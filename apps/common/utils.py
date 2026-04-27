def generate_unique_id(prefix, model):
    last_obj = model.objects.filter(uid__startswith=prefix).order_by('-id').first()

    next_id = 1
    if last_obj and last_obj.uid:
        try:
            numeric_part = last_obj.uid[len(prefix):]
            if numeric_part.isdigit():
                next_id = int(numeric_part) + 1
        except (ValueError, IndexError):
            pass

    while True:
        new_uid = f"{prefix}{next_id:06d}" 
        if not model.objects.filter(uid=new_uid).exists():
            return new_uid
        next_id += 1