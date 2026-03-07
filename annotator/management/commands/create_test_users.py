from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "1 ta admin va 5 ta testlovchi user yaratadi"

    def handle(self, *args, **options):
        User = get_user_model()

        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={"role": "admin", "is_staff": True, "is_superuser": True},
        )
        admin.role = "admin"
        admin.is_staff = True
        admin.is_superuser = True
        admin.set_password("admin12345")
        admin.save()
        self.stdout.write(self.style.SUCCESS("admin / admin12345 tayyor"))

        for i in range(1, 6):
            user, _ = User.objects.get_or_create(username=f"tester{i}", defaults={"role": "annotator"})
            user.role = "annotator"
            user.is_staff = False
            user.is_superuser = False
            user.set_password(f"tester{i}12345")
            user.save()
            self.stdout.write(self.style.SUCCESS(f"tester{i} / tester{i}12345 tayyor"))
