
def user_avatar_path(instance, filename):
    return f"users/avatars/user_{instance.id}/{filename}"

def passport_path(instance, filename):
    return f"users/passports/user_{instance.id}/{filename}"