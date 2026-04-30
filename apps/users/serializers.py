from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenRefreshSerializer, TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.applications.models import Region, District, Position
from apps.applications.serializers import RegionSerializer, DistrictSerializer, PositionSerializer
from apps.projects.models import TaskStatus, ProjectStatus
from apps.users.models import Role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    confirm_password = serializers.CharField(write_only=True, required=False)

    region_info = RegionSerializer(source='region', read_only=True)
    district_info = DistrictSerializer(source='district', read_only=True)
    position_info = PositionSerializer(source='position', read_only=True)

    region = serializers.PrimaryKeyRelatedField(queryset=Region.objects.all(), write_only=True)
    district = serializers.PrimaryKeyRelatedField(queryset=District.objects.all(), write_only=True)
    position = serializers.PrimaryKeyRelatedField(queryset=Position.objects.all(), required=False, write_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'avatar', 'username', 'phone_number', 'card_number', 'region', 'region_info', 'district',
            'district_info', 'position', 'position_info',
            'passport_series', 'passport_image', 'social_links', 'roles',
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

        input_roles = attrs.get('roles', [])
        password = attrs.get('password')
        confirm_password = attrs.get('confirm_password')

        if current_user.has_role(Role.ADMIN) and not current_user.has_role(Role.SUPERADMIN):
            if Role.SUPERADMIN in input_roles:
                raise serializers.ValidationError({
                    "roles": "Siz Super Admin yarata olmaysiz."
                })

            if self.instance and self.instance.has_role(Role.SUPERADMIN):
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
            instance.change_password = True

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
        return self._get_stats(instance, days)

    def _get_stats(self, obj, days):
        now = timezone.now()
        start_date = now - timedelta(days=days)

        active_task_statuses = [
            TaskStatus.TODO,
            TaskStatus.IN_PROGRESS,
            TaskStatus.OVERDUE
        ]

        task_filter = Q(updated_at__gte=start_date) | Q(status__in=active_task_statuses)
        filtered_tasks = obj.tasks.filter(task_filter)

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
        t_rate = round((t_completed / t_total * 100), 1) if t_total > 0 else 100.0

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

        all_projects = (obj.manager_projects.all() | obj.employee_projects.all()).distinct()

        active_project_statuses = [
            ProjectStatus.PLANNING, 
            ProjectStatus.ACTIVE,
            ProjectStatus.OVERDUE
        ]
        project_filter = Q(updated_at__gte=start_date) | Q(status__in=active_project_statuses)
        filtered_projects = all_projects.filter(project_filter)

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
        p_rate = round((p_completed / p_total * 100), 1) if p_total > 0 else 100.0

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

        filtered_meetings = obj.attendances.filter(created_at__gte=start_date)

        m_stats = filtered_meetings.aggregate(
            total=Count('id'),
            attended=Count('id', filter=Q(is_attended=True)),
            missed=Count('id', filter=Q(is_attended=False)),
            with_reason=Count('id', filter=Q(is_attended=False) & ~Q(absence_reason__exact='') & Q(
                absence_reason__isnull=False)),
        )

        m_total = m_stats['total'] or 0
        m_attended = m_stats['attended'] or 0
        m_missed = m_stats['missed'] or 0
        m_with_reason = m_stats['with_reason'] or 0

        meetings_data = {
            "total": m_total,
            "attended": m_attended,
            "missed": m_missed,
            "with_reason": m_with_reason,
            "unexcused": m_missed - m_with_reason,
            "attendance_rate": round((m_attended / m_total * 100), 1) if m_total > 0 else 100.0
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

    def _calculate_efficiency(self, obj, days):
        now = timezone.now()
        start_date = now - timedelta(days=days)

        active_task_statuses = [
            TaskStatus.TODO,
            TaskStatus.IN_PROGRESS,
            TaskStatus.OVERDUE
        ]

        task_filter = Q(updated_at__gte=start_date) | Q(status__in=active_task_statuses)
        filtered_tasks = obj.tasks.filter(task_filter)

        t_stats = filtered_tasks.aggregate(
            total=Count('id'),
            overdue=Count('id', filter=Q(status=TaskStatus.OVERDUE)),
            rejected=Count('id', filter=Q(reopened_count__gt=0)),
        )

        total_tasks = t_stats['total'] or 0
        overdue_tasks = t_stats['overdue'] or 0
        rejected_tasks = t_stats['rejected'] or 0

        if total_tasks > 0:
            task_timeliness = 100.0 * (total_tasks - overdue_tasks) / total_tasks
            task_quality = 100.0 * (total_tasks - rejected_tasks) / total_tasks
            task_score = (task_timeliness + task_quality) / 2.0
        else:
            task_score = 0.0

        filtered_meetings = obj.attendances.filter(created_at__gte=start_date)

        m_stats = filtered_meetings.aggregate(
            total=Count('id'),
            missed=Count('id', filter=Q(is_attended=False)),
            with_reason=Count('id', filter=Q(is_attended=False) & ~Q(absence_reason__exact='') & Q(absence_reason__isnull=False)),
        )

        total_meetings = m_stats['total'] or 0
        missed = m_stats['missed'] or 0
        with_reason = m_stats['with_reason'] or 0
        unexcused_meetings = missed - with_reason

        if total_meetings > 0:
            meeting_score = 100.0 * (total_meetings - unexcused_meetings) / total_meetings
        else:
            meeting_score = 0.0

        active_project_statuses = [
            ProjectStatus.PLANNING, 
            ProjectStatus.ACTIVE,
            ProjectStatus.OVERDUE
        ]
        project_filter = Q(updated_at__gte=start_date) | Q(status__in=active_project_statuses)
        managed_projects = obj.manager_projects.filter(project_filter)

        p_stats = managed_projects.aggregate(
            total=Count('id'),
            overdue=Count('id', filter=Q(status=ProjectStatus.OVERDUE))
        )

        total_projects = p_stats['total'] or 0
        overdue_projects = p_stats['overdue'] or 0

        if total_projects > 0:
            project_score = 100.0 * (total_projects - overdue_projects) / total_projects
        else:
            project_score = 0.0

        w_task = 0.0
        w_project = 0.0
        w_meeting = 0.0

        if total_projects > 0:
            w_task = 0.4
            w_project = 0.4
            w_meeting = 0.2
        else:
            w_task = 0.8
            w_meeting = 0.2

        total_weight = 0.0
        earned_score = 0.0

        if total_tasks > 0:
            earned_score += task_score * w_task
            total_weight += w_task

        if total_projects > 0:
            earned_score += project_score * w_project
            total_weight += w_project

        if total_meetings > 0:
            earned_score += meeting_score * w_meeting
            total_weight += w_meeting

        if total_weight == 0.0:
            overall_efficiency = 100.0
        else:
            overall_efficiency = earned_score / total_weight

        return {
            "overall_efficiency": round(overall_efficiency, 1),
            "task_score": round(task_score, 1),
            "project_score": round(project_score, 1),
            "meeting_score": round(meeting_score, 1),
            "metrics": {
                "total_tasks": total_tasks,
                "overdue_tasks": overdue_tasks,
                "rejected_tasks": rejected_tasks,
                "total_projects": total_projects,
                "overdue_projects": overdue_projects,
                "total_meetings": total_meetings,
                "unexcused_meetings": unexcused_meetings
            }
        }


class UserShortSerializer(serializers.ModelSerializer):
    region = serializers.CharField(source='region.name', read_only=True, default=None)
    district = serializers.CharField(source='district.name', read_only=True, default=None)
    position = serializers.CharField(source='position.name', read_only=True, default=None)

    class Meta:
        model = User
        fields = ('id', 'avatar', 'username', 'phone_number', 'card_number',
                  'region', 'district', 'position', 'roles', 'date_joined')


class ProfileSerializer(serializers.ModelSerializer):
    region = serializers.CharField(source='region.name', read_only=True, default=None)
    district = serializers.CharField(source='district.name', read_only=True, default=None)
    position = serializers.CharField(source='position.name', read_only=True, default=None)

    class Meta:
        model = User
        fields = ('id', 'avatar', 'username', 'phone_number', 'card_number',
                  'passport_series', 'passport_image', 'region', 'district',
                  'position', 'roles', 'fixed_salary', 'balance', 'social_links',
                  'date_joined', 'change_password')


class SocialLinksSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('social_links',)


class CardNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('card_number',)


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
            "date_joined": user.date_joined,
            "change_password": user.change_password,
        }

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
                "date_joined": user.date_joined,
                "change_password": user.change_password,
            }
        except User.DoesNotExist:
            pass

        return data
