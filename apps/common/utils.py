def generate_unique_id(prefix, model):
    last_obj = model.objects.only('uid').order_by('-uid').first()

    if not last_obj or not last_obj.uid:
        next_id = 1
    else:
        try:
            numeric_part = "".join(filter(str.isdigit, last_obj.uid))
            if numeric_part:
                next_id = int(numeric_part) + 1
            else:
                next_id = 1
        except (ValueError, TypeError):
            next_id = 1

    return f"{prefix}{next_id:06d}"