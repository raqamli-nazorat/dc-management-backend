from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.utils import timezone

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenRefreshSerializer, TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.applications.models import Region, District, Position
from apps.notifications.models import Notification, NotificationType
from apps.applications.serializers import RegionSerializer, DistrictSerializer, PositionSerializer
from apps.projects.models import TaskStatus, ProjectStatus, Task, Project, MeetingAttendance
from apps.users.models import Role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    confirm_password = serializers.CharField(write_only=True, required=False)

    region_info = RegionSerializer(source='region', read_only=True)
    district_info = DistrictSerializer(source='district', read_only=True)
    position_info = PositionSerializer(source='position', read_only=True)

    region = serializers.PrimaryKeyRelatedField(queryset=Region.objects.all(), write_only=True)
    district = serializers.PrimaryKeyRelatedField(queryset=District.objects.all(), required=False, write_only=True)
    position = serializers.PrimaryKeyRelatedField(queryset=Position.objects.all(), required=False, write_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'avatar', 'username', 'phone_number', 'card_number', 'region', 'region_info', 'district',
            'district_info', 'position', 'position_info',
            'passport_series', 'passport_image', 'social_links', 'roles', 'active_role',
            'password', 'confirm_password',
            'fixed_salary', 'balance'
        )
        read_only_fields = ('id', 'balance')
        extra_kwargs = {
            'username': {'validators': []}
        }

    def validate_username(self, value):
        instance = self.instance

        if instance and instance.username == value:
            return value

        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Bu username allaqachon band. Iltimos, boshqasini tanlang.")

        return value

    def validate(self, attrs):
        request = self.context.get('request')
        current_user = request.user

        password = attrs.get('password')
        confirm_password = attrs.get('confirm_password')

        if current_user.has_role(Role.ADMIN) and not current_user.is_superuser:
            if self.instance and self.instance.is_superuser:
                raise serializers.ValidationError({
                    "detail": "Super Admin ma'lumotlarini o'zgartirish huquqi sizda yo'q."
                })

        if password is not None:
            if not password.isdigit():
                raise serializers.ValidationError({"password": "Parol faqat raqamlardan iborat bo'lishi kerak."})
            if password != confirm_password:
                raise serializers.ValidationError({"password": "Parollar mos kelmayapti."})

        return attrs

    def create(self, validated_data):
        validated_data.pop('confirm_password', None)
        password = validated_data.pop('password', None)

        user = User(**validated_data)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save()
        return user

    def update(self, instance, validated_data):
        validated_data.pop('confirm_password', None)
        password = validated_data.pop('password', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.full_clean()

        instance.save()
        return instance


class UserPeriodStatsSerializer(serializers.Serializer):
    def to_representation(self, instance):
        request = self.context.get('request')
        months = 1
        if request and request.query_params:
            try:
                months = int(request.query_params.get('months', 1))
                if months <= 0:
                    months = 1
            except (ValueError, TypeError):
                months = 1

        days = months * 30
        return self._get_stats(request.user, days)

    def _get_stats(self, user, days):
        is_privileged = user.is_superuser or user.has_role(Role.ADMIN, Role.AUDITOR)
        is_manager = user.has_role(Role.MANAGER)

        now = timezone.now()
        start_date = now - timedelta(days=days)

        active_project_statuses = [ProjectStatus.PLANNING, ProjectStatus.ACTIVE, ProjectStatus.OVERDUE]
        p_base_filter = Q(updated_at__gte=start_date) | Q(status__in=active_project_statuses)
        p_common_kwargs = {
            'is_active': True,
            'is_deleted': False,
            'is_hidden': False
        }

        if is_privileged:
            filtered_projects = Project.objects.filter(p_base_filter, **p_common_kwargs)
        elif is_manager:
            filtered_projects = Project.objects.filter(
                p_base_filter, manager=user, **p_common_kwargs
            )
        else:
            filtered_projects = Project.objects.filter(
                p_base_filter,
                Q(employees=user) | Q(testers=user),
                **p_common_kwargs
            ).distinct()

        p_stats = filtered_projects.aggregate(
            total=Count('id'),
            planning=Count('id', filter=Q(status=ProjectStatus.PLANNING)),
            active=Count('id', filter=Q(status=ProjectStatus.ACTIVE)),
            overdue=Count('id', filter=Q(status=ProjectStatus.OVERDUE)),
            completed=Count('id', filter=Q(status=ProjectStatus.COMPLETED)),
            cancelled=Count('id', filter=Q(status=ProjectStatus.CANCELLED)),
        )

        p_total = p_stats['total'] or 0
        p_completed = p_stats['completed'] or 0
        p_rate = round((p_completed / p_total * 100), 1) if p_total > 0 else 0.0

        projects_data = {
            "total": p_total,
            "planning": p_stats['planning'] or 0,
            "active": p_stats['active'] or 0,
            "overdue": p_stats['overdue'] or 0,
            "completed": p_completed,
            "cancelled": p_stats['cancelled'] or 0,
            "current_work": (p_stats['planning'] or 0) + (p_stats['active'] or 0) + (p_stats['overdue'] or 0),
            "completion_rate": p_rate
        }

        active_task_statuses = [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.OVERDUE]
        t_base_filter = Q(updated_at__gte=start_date) | Q(status__in=active_task_statuses)
        t_common_kwargs = {
            'is_active': True,
            'is_deleted': False,
            'project__is_hidden': False,
            'project__is_active': True,
            'project__is_deleted': False
        }

        if is_privileged:
            filtered_tasks = Task.objects.filter(t_base_filter, **t_common_kwargs)
        elif is_manager:
            filtered_tasks = Task.objects.filter(
                t_base_filter, project__manager=user, **t_common_kwargs
            )
        else:
            filtered_tasks = Task.objects.filter(
                t_base_filter,
                Q(project__employees=user) | Q(project__testers=user),
                assignee=user,
                **t_common_kwargs
            ).distinct()

        t_stats = filtered_tasks.aggregate(
            total=Count('id'),
            todo=Count('id', filter=Q(status=TaskStatus.TODO)),
            in_progress=Count('id', filter=Q(status=TaskStatus.IN_PROGRESS)),
            overdue=Count('id', filter=Q(status=TaskStatus.OVERDUE)),
            done=Count('id', filter=Q(status=TaskStatus.DONE)),
            checked=Count('id', filter=Q(status=TaskStatus.CHECKED)),
            production=Count('id', filter=Q(status=TaskStatus.PRODUCTION)),
            rejected=Count('id', filter=Q(reopened_count__gt=0)),
            total_rejections=Sum('reopened_count')
        )

        t_total = t_stats['total'] or 0
        t_completed = (t_stats['done'] or 0) + (t_stats['checked'] or 0) + (t_stats['production'] or 0)
        t_rate = round((t_completed / t_total * 100), 1) if t_total > 0 else 0.0

        tasks_data = {
            "total": t_total,
            "todo": t_stats['todo'] or 0,
            "in_progress": t_stats['in_progress'] or 0,
            "overdue": t_stats['overdue'] or 0,
            "done": t_stats['done'] or 0,
            "checked": t_stats['checked'] or 0,
            "production": t_stats['production'] or 0,
            "rejected_tasks": t_stats['rejected'] or 0,
            "total_rejections": t_stats['total_rejections'] or 0,
            "overall_completed": t_completed,
            "completion_rate": t_rate
        }

        m_base_filter = {
            'created_at__gte': start_date,
            'is_active': True,
            'meeting__is_active': True,
            'meeting__is_deleted': False,
        }
        m_project_filter = Q(meeting__project__isnull=True) | Q(meeting__project__is_hidden=False)

        if is_privileged:
            filtered_meetings = MeetingAttendance.objects.filter(
                m_project_filter, **m_base_filter
            ).distinct()
        elif is_manager:
            filtered_meetings = MeetingAttendance.objects.filter(
                meeting__project__manager=user, **m_base_filter
            ).distinct()
        else:
            filtered_meetings = MeetingAttendance.objects.filter(
                m_project_filter, user=user, **m_base_filter
            ).distinct()

        m_stats = filtered_meetings.aggregate(
            total=Count('id'),
            attended=Count('id', filter=Q(is_attended=True)),
            missed=Count('id', filter=Q(is_attended=False)),
            with_reason=Count('id', filter=Q(is_attended=False) & Q(is_excused=True)),
            total_duration=Sum('meeting__duration_minutes', filter=Q(is_attended=True)),
            unique_participants=Count('user', distinct=True),
            unique_meetings=Count('meeting', distinct=True)
        )

        m_total = m_stats['total'] or 0
        m_attended = m_stats['attended'] or 0
        m_missed = m_stats['missed'] or 0

        meetings_data = {
            "total": m_total,
            "attended": m_attended,
            "missed": m_missed,
            "with_reason": m_stats['with_reason'] or 0,
            "unexcused": m_missed - (m_stats['with_reason'] or 0),
            "total_duration_minutes": m_stats['total_duration'] or 0,
            "unique_participants": m_stats['unique_participants'] or 0,
            "unique_meetings": m_stats['unique_meetings'] or 0,
            "attendance_rate": round((m_attended / m_total * 100), 1) if m_total > 0 else 0.0
        }

        return {
            "projects": projects_data,
            "tasks": tasks_data,
            "meetings": meetings_data
        }


class UserEfficiencySerializer(serializers.Serializer):
    def to_representation(self, instance):
        request = self.context.get('request')
        months = 1
        if request and request.query_params:
            try:
                months = int(request.query_params.get('months', 1))
                if months <= 0:
                    months = 1
            except (ValueError, TypeError):
                months = 1

        days = months * 30
        return self._calculate_efficiency(instance, days)

    def _generate_insights(self, data, obj_is_manager):
        insights = []
        metrics = data['metrics']

        total_tasks = metrics.get('total_tasks', 0)
        overdue_tasks = metrics.get('overdue_tasks', 0)
        rejected_tasks = metrics.get('rejected_tasks', 0)
        total_reopened = metrics.get('total_reopened_actions', 0)

        if total_tasks > 0:
            overdue_pct = overdue_tasks / total_tasks * 100
            rejected_pct = rejected_tasks / total_tasks * 100

            if overdue_pct >= 50:
                if obj_is_manager:
                    insights.append(
                        f"Loyihalaridagi vazifalarning {round(overdue_pct)}%i muddati o'tib ketgan — nazorat yetarli emas.")
                else:
                    insights.append(f"Vazifalarning {round(overdue_pct)}%i muddati o'tib ketgan.")
            elif overdue_pct >= 20:
                if obj_is_manager:
                    insights.append(f"Loyihalaridagi vazifalarning {round(overdue_pct)}%i kechikmoqda.")
                else:
                    insights.append(f"Vazifalarning {round(overdue_pct)}%i kechikmoqda.")

            if not obj_is_manager:
                if rejected_pct >= 30:
                    insights.append(f"Vazifalarning {round(rejected_pct)}%i qayta ochilgan — sifat past.")
                elif rejected_pct >= 10:
                    insights.append(f"Vazifalarning {round(rejected_pct)}%i bir marta qaytarilgan.")

                if total_reopened > total_tasks:
                    insights.append(
                        f"O'rtacha har bir vazifa {round(total_reopened / total_tasks, 1)} marta qayta ochilgan.")

        total_meetings = metrics.get('total_meetings', 0)
        unexcused_meetings = metrics.get('unexcused_meetings', 0)

        if total_meetings > 0:
            unexcused_pct = unexcused_meetings / total_meetings * 100
            if unexcused_pct >= 50:
                insights.append(f"Uchrashuvlarning {round(unexcused_pct)}%i sababsiz o'tkazib yuborilgan.")
            elif unexcused_pct >= 20:
                insights.append(f"Uchrashuvlarning {round(unexcused_pct)}%i qatnashilmagan.")

        if obj_is_manager:
            total_projects = metrics.get('total_projects', 0)
            overdue_projects = metrics.get('overdue_projects', 0)

            if total_projects > 0:
                overdue_p_pct = overdue_projects / total_projects * 100
                if overdue_p_pct >= 50:
                    insights.append(f"Loyihalarning {round(overdue_p_pct)}%i muddati o'tib ketgan.")
                elif overdue_p_pct >= 20:
                    insights.append(f"Loyihalarning {round(overdue_p_pct)}%i kechikmoqda.")

        if not insights:
            has_data = total_tasks > 0 or total_meetings > 0
            if obj_is_manager:
                has_data = has_data or metrics.get('total_projects', 0) > 0

            if not has_data:
                insights.append("Ma'lumot yetarli emas.")
            else:
                insights.append("Hamma ko'rsatkichlar yaxshi darajada.")

        return insights

    def _calculate_efficiency(self, obj, days):
        now = timezone.now()
        start_date = now - timedelta(days=days)
        obj_is_manager = obj.has_role(Role.MANAGER)

        task_filter = (
                Q(status__in=[TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.OVERDUE]) |
                Q(updated_at__gte=start_date)
        )
        t_common_kwargs = {
            'is_active': True,
            'is_deleted': False,
            'project__is_hidden': False,
            'project__is_active': True,
            'project__is_deleted': False,
            'project__status__in': [
                ProjectStatus.ACTIVE,
                ProjectStatus.OVERDUE,
                ProjectStatus.COMPLETED,
            ]
        }

        if obj_is_manager:
            filtered_tasks = Task.objects.filter(
                task_filter,
                project__manager=obj,
                **t_common_kwargs
            )
        else:
            filtered_tasks = obj.tasks.filter(task_filter, **t_common_kwargs)

        t_stats = filtered_tasks.aggregate(
            total=Count('id'),
            overdue=Count('id', filter=Q(status=TaskStatus.OVERDUE)),
            rejected=Count('id', filter=Q(reopened_count__gt=0)),
            total_reopened=Sum('reopened_count')
        )

        total_tasks = t_stats['total'] or 0
        overdue_tasks = t_stats['overdue'] or 0
        rejected_tasks = t_stats['rejected'] or 0

        meeting_base_filter = {
            'created_at__gte': start_date,
            'is_active': True,
            'meeting__is_active': True,
            'meeting__is_deleted': False,
        }

        if obj_is_manager:
            filtered_meetings = MeetingAttendance.objects.filter(
                meeting__project__manager=obj,
                meeting__project__is_hidden=False,
                **meeting_base_filter
            ).exclude(meeting__organizer=obj)
        else:
            filtered_meetings = obj.attendances.filter(
                Q(meeting__project__isnull=True) | Q(meeting__project__is_hidden=False),
                **meeting_base_filter
            )

        m_stats = filtered_meetings.aggregate(
            total=Count('id'),
            missed=Count('id', filter=Q(is_attended=False)),
            with_reason=Count('id', filter=Q(is_attended=False) & Q(is_excused=True)),
        )

        total_meetings = m_stats['total'] or 0
        missed = m_stats['missed'] or 0
        unexcused_meetings = missed - (m_stats['with_reason'] or 0)

        meeting_score = round(
            100.0 * (total_meetings - unexcused_meetings) / total_meetings, 1
        ) if total_meetings > 0 else 0.0

        if obj_is_manager:
            project_filter = (
                    Q(status__in=[ProjectStatus.ACTIVE, ProjectStatus.OVERDUE, ProjectStatus.COMPLETED]) |
                    Q(updated_at__gte=start_date)
            )

            managed_projects = obj.manager_projects.filter(
                project_filter,
                is_active=True,
                is_deleted=False,
                is_hidden=False
            )

            p_stats = managed_projects.aggregate(
                total=Count('id'),
                overdue=Count('id', filter=Q(status=ProjectStatus.OVERDUE)),
            )

            total_p = p_stats['total'] or 0
            overdue_p = p_stats['overdue'] or 0

            project_timeliness = 100.0 * (total_p - overdue_p) / total_p if total_p > 0 else 0.0
            task_timeliness = 100.0 * (total_tasks - overdue_tasks) / total_tasks if total_tasks > 0 else 0.0

            if total_p > 0 and total_tasks > 0:
                supervision_score = (project_timeliness * 0.4) + (task_timeliness * 0.6)
            elif total_p > 0:
                supervision_score = project_timeliness
            elif total_tasks > 0:
                supervision_score = task_timeliness
            else:
                supervision_score = 0.0

            earned_score = 0.0
            total_weight = 0.0

            if total_p > 0 or total_tasks > 0:
                earned_score += supervision_score * 0.70
                total_weight += 0.70

            if total_meetings > 0:
                earned_score += meeting_score * 0.30
                total_weight += 0.30

            overall_efficiency = round(earned_score / total_weight, 1) if total_weight > 0 else 0.0

            result = {
                "overall_efficiency": overall_efficiency,
                "supervision_score": round(supervision_score, 1),
                "meeting_score": meeting_score,
                "metrics": {
                    "total_projects": total_p,
                    "overdue_projects": overdue_p,
                    "total_tasks": total_tasks,
                    "overdue_tasks": overdue_tasks,
                    "total_meetings": total_meetings,
                    "unexcused_meetings": unexcused_meetings
                }
            }

        else:
            if total_tasks > 0:
                task_timeliness = 100.0 * (total_tasks - overdue_tasks) / total_tasks
                task_quality = 100.0 * (total_tasks - rejected_tasks) / total_tasks
                task_score = (task_timeliness + task_quality) / 2.0
            else:
                task_score = 0.0

            earned_score = 0.0
            total_weight = 0.0

            if total_tasks > 0:
                earned_score += task_score * 0.80
                total_weight += 0.80

            if total_meetings > 0:
                earned_score += meeting_score * 0.20
                total_weight += 0.20

            overall_efficiency = round(earned_score / total_weight, 1) if total_weight > 0 else 0.0

            result = {
                "overall_efficiency": overall_efficiency,
                "task_score": round(task_score, 1),
                "meeting_score": meeting_score,
                "metrics": {
                    "total_tasks": total_tasks,
                    "overdue_tasks": overdue_tasks,
                    "rejected_tasks": rejected_tasks,
                    "total_reopened_actions": t_stats['total_reopened'] or 0,
                    "total_meetings": total_meetings,
                    "unexcused_meetings": unexcused_meetings
                }
            }

        result["insights"] = self._generate_insights(result, obj_is_manager)
        return result


class UserShortSerializer(serializers.ModelSerializer):
    region = serializers.CharField(source='region.name', read_only=True, default=None)
    district = serializers.CharField(source='district.name', read_only=True, default=None)
    position = serializers.CharField(source='position.name', read_only=True, default=None)

    class Meta:
        model = User
        fields = ('id', 'avatar', 'username', 'phone_number', 'card_number',
                  'region', 'district', 'position', 'roles', 'active_role', 'date_joined')


class ProfileSerializer(serializers.ModelSerializer):
    region = serializers.CharField(source='region.name', read_only=True, default=None)
    district = serializers.CharField(source='district.name', read_only=True, default=None)
    position = serializers.CharField(source='position.name', read_only=True, default=None)

    class Meta:
        model = User
        fields = ('id', 'avatar', 'username', 'phone_number', 'card_number',
                  'passport_series', 'passport_image', 'region', 'district',
                  'position', 'roles', 'active_role', 'fixed_salary', 'balance', 'social_links',
                  'date_joined')
        read_only_fields = ('id', 'username', 'passport_series', 'passport_image', 'region', 'district',
                            'position', 'roles', 'fixed_salary', 'balance',
                            'date_joined')

    def validate(self, attrs):
        instance = self.instance

        if instance:
            for attr, value in attrs.items():
                setattr(instance, attr, value)

            instance.full_clean()

        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True,
        min_length=4,
        error_messages={
            'min_length': "Parol kamida 4 ta raqamdan iborat bo'lishi kerak."
        })

    confirm_new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Eski parol noto'g'ri.")
        return value

    def validate(self, attrs):
        new_password = attrs.get('new_password')
        confirm_new_password = attrs.get('confirm_new_password')
        old_password = attrs.get('old_password')

        if not new_password.isdigit():
            raise serializers.ValidationError({
                'new_password': "Parol faqat raqamlardan iborat bo'lishi kerak."
            })

        if new_password != confirm_new_password:
            raise serializers.ValidationError({
                'new_password': "Yangi parol maydonlari mos kelmadi."
            })

        if old_password == new_password:
            raise serializers.ValidationError({
                'new_password': "Yangi parol eskisidan farq qilishi kerak."
            })

        return attrs

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.change_password = False
        user.save()
        return user


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data: dict = super().validate(attrs)
        user = self.user

        data["user"] = {
            "id": user.id,
            "avatar": user.avatar.url if user.avatar else None,
            "username": user.username,
            "phone_number": user.phone_number,
            "region": user.region.name if user.region else None,
            "district": user.district.name if user.district else None,
            "position": user.position.name if user.position else None,
            "roles": user.roles,
            "active_role": user.active_role,
            "date_joined": user.date_joined
        }

        if user.change_password:
            Notification.objects.get_or_create(
                user=user,
                title="Parolingizni yangilang",
                message="Xavfsizlik nuqtai nazaridan parolingizni yangilashingizni so'raymiz.",
                type=NotificationType.SYSTEM
            )

        return data


class MyTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        data: dict = super().validate(attrs)

        refresh = RefreshToken(attrs["refresh"])
        user_id = refresh.get("user_id")

        try:
            user = User.objects.get(id=user_id)
            data["user"] = {
                "id": user.id,
                "avatar": user.avatar.url if user.avatar else None,
                "username": user.username,
                "phone_number": user.phone_number,
                "region": user.region.name if user.region else None,
                "district": user.district.name if user.district else None,
                "position": user.position.name if user.position else None,
                "roles": user.roles,
                "active_role": user.active_role,
                "date_joined": user.date_joined
            }
        except User.DoesNotExist:
            pass

        return data
