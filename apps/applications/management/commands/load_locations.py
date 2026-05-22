from django.core.management.base import BaseCommand
from apps.applications.models import Region, District


class Command(BaseCommand):
    help = "O'zbekistonning barcha viloyat va tumanlarini bazaga avtomatik kiritish"

    def handle(self, *args, **options):
        data = {
            "Andijon viloyati": [
                "Oltinko'l tumani", "Andijon tumani", "Baliqchi tumani", "Bo'z tumani",
                "Buloqboshi tumani", "Jalaquduq tumani", "Izboskan tumani", "Ulug'nor tumani",
                "Qo'rg'ontepa tumani", "Asaka tumani", "Marxamat tumani", "Shahrixon tumani",
                "Paxtaobod tumani", "Xo'jaobod tumani", "Andijon", "Xonobod"
            ],
            "Buxoro viloyati": [
                "Olot tumani", "Buxoro tumani", "Vobkent tumani", "G'ijduvon tumani",
                "Kogon tumani", "Qorako'l tumani", "Qorovulbozor tumani", "Peshku tumani",
                "Romitan tumani", "Jondor tumani", "Shofirkon tumani", "Buxoro", "Kogon"
            ],
            "Jizzax viloyati": [
                "Arnasoy tumani", "Baxmal tumani", "G'allaorol tumani", "Do'stlik tumani",
                "Zomin tumani", "Zarbdor tumani", "Mirzacho'l tumani", "Zafarobod tumani",
                "Paxtakor tumani", "Forish tumani", "Yangiobod tumani", "Jizzax", "Sh.Rashidov tumani"
            ],
            "Qashqadaryo viloyati": [
                "G'uzor tumani", "Dehqonobod tumani", "Qamashi tumani", "Qarshi tumani",
                "Koson tumani", "Kitob tumani", "Mirishkor tumani", "Muborak tumani",
                "Nishon tumani", "Kasbi tumani", "Chiroqchi tumani", "Shahrisabz tumani",
                "Yakkabog' tumani", "Qarshi", "Shahrisabz", "Ko‘kdala tumani"
            ],
            "Navoiy viloyati": [
                "Konimex tumani", "Qiziltepa tumani", "Navbahor tumani", "Karmana tumani",
                "Nurota tumani", "Tomdi tumani", "Uchquduq tumani", "Xatirchi tumani",
                "Navoiy", "Zarafshon", "G‘ozg‘on tumani"
            ],
            "Namangan viloyati": [
                "Mingbuloq tumani", "Kosonsoy tumani", "Namangan tumani", "Norin tumani",
                "Pop tumani", "To'raqo'rg'on tumani", "Uychi tumani", "Uchqo'rg'on tumani",
                "Chortoq tumani", "Chust tumani", "Yangiqo'rg'on tumani", "Namangan",
                "Davlatobod tumani", "Yangi Namangan tumani"
            ],
            "Samarqand viloyati": [
                "Oqdaryo tumani", "Bulung'ur tumani", "Jomboy tumani", "Ishtixon tumani",
                "Kattaqo'rg'on tumani", "Qo'shrabot tumani", "Narpay tumani", "Payariq tumani",
                "Pastdarg'om tumani", "Paxtachi tumani", "Samarqand tumani", "Nurobod tumani",
                "Urgut tumani", "Tayloq tumani", "Samarqand", "Kattaqo'rg'on"
            ],
            "Sirdaryo viloyati": [
                "Oqoltin tumani", "Boyovut tumani", "Sayxunobod tumani", "Guliston tumani",
                "Sardoba tumani", "Mirzaobod tumani", "Sirdaryo tumani", "Xovos tumani",
                "Guliston", "Shirin", "Yangiyer", "Baxt shaxar"
            ],
            "Toshkent shahri": [
                "Uchtepa tumani", "Bektemir tumani", "Yunusobod tumani", "Mirzo Ulug'bek tumani",
                "Mirobod tumani", "Shayxontohur tumani", "Olmazor tumani", "Sirg'ali tumani",
                "Yakkasaroy tumani", "Yashnobod tumani", "Chilonzor tumani",
                "Toshkent shahrining tumanlari", "Yangihayot tumani"
            ],
            "Toshkent viloyati": [
                "Oqqo'rg'on tumani", "Ohangaron tumani", "Bekobod tumani", "Bo'stonliq tumani",
                "Bo'ka tumani", "Zangiota tumani", "Yuqorichirchiq tumani", "Qibray tumani",
                "Parkent tumani", "Piskent tumani", "O'rtachirchiq tumani", "Chinoz tumani",
                "Yangiyo'l tumani", "Toshkent tumani", "Nurafshon", "Olmaliq", "Angren",
                "Bekobod", "Ohangaron", "Chirchiq", "Yangiyo'l", "Quyichirchiq tumani"
            ],
            "Farg'ona viloyati": [
                "Oltiariq tumani", "Qo'shtepa tumani", "Bog'dod tumani", "Buvayda tumani",
                "Beshariq tumani", "Quva tumani", "Uchko'prik tumani", "Rishton tumani",
                "So'x tumani", "Toshloq tumani", "O'zbekiston tumani", "Farg'ona tumani",
                "Dang'ara tumani", "Furqat tumani", "Yozyovon tumani", "Farg'ona",
                "Qo'qon", "Quvasoy", "Marg'ilon"
            ],
            "Xorazm viloyati": [
                "Bog'ot tumani", "Gurlan tumani", "Qo'shko'pir tumani", "Urganch tumani",
                "Xazorasp tumani", "Xonqa tumani", "Xiva tumani", "Shovot tumani",
                "Yangiariq tumani", "Yangibozor tumani", "Urganch", "Xiva", "Tuproqqal’a tumani"
            ],
            "Qoraqalpog'iston Respublikasi": [
                "Amudaryo tumani", "Beruniy tumani", "Qorao'zak tumani", "Kegeyli tumani",
                "Qo'ng'irot tumani", "Qanliko'l tumani", "Mo'ynoq tumani", "Nukus tumani",
                "Taxiatosh tumani", "Taxtako'pir tumani", "To'rtko'l tumani", "Xo'jayli tumani",
                "Chimboy tumani", "Shumanay tumani", "Ellikqal'a tumani", "Nukus", "Bo‘zatov tumani"
            ],
            "Surxondaryo viloyati": [
                "Oltinsoy tumani", "Angor tumani", "Boysun tumani", "Muzrabot tumani",
                "Denov tumani", "Jarqo'rg'on tumani", "Qumqo'rg'on tumani", "Qiziriq tumani",
                "Sariosiyo tumani", "Termiz tumani", "Uzun tumani", "Sherobod tumani",
                "Sho'rchi tumani", "Termiz", "Bandixon tumani"
            ]
        }

        region_count = 0
        district_count = 0

        for region_name, districts_list in data.items():
            region, created = Region.objects.get_or_create(name=region_name)
            if created:
                region_count += 1

            for district_name in districts_list:
                district, dist_created = District.objects.get_or_create(
                    name=district_name,
                    region=region
                )
                if dist_created:
                    district_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Tayyor! {region_count} ta viloyat va {district_count} ta tuman/shahar bazaga yozildi."))
