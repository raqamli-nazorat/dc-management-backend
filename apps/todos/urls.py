from rest_framework.routers import SimpleRouter

from .views import TodoViewSet, TodoItemViewSet

router = SimpleRouter()
router.register('todos', TodoViewSet)
router.register('todo-items', TodoItemViewSet, basename='todo-items')

urlpatterns = router.urls
