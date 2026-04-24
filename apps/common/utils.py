def generate_unique_id(prefix, model):
    last_obj = model.objects.only('uid').order_by('-id').first()

    next_id = 1
    if last_obj and getattr(last_obj, 'uid', None):
        try:
            numeric_part = "".join(filter(str.isdigit, str(last_obj.uid)))
            if numeric_part:
                next_id = int(numeric_part) + 1
        except (ValueError, TypeError):
            pass

    while True:
        new_uid = f"{prefix}{next_id:06d}"
        if not model.objects.filter(uid=new_uid).exists():
            return new_uid
        next_id += 1