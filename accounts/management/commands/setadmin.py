from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "Grant (or with --remove revoke) admin rights for a registered member."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--remove", action="store_true", help="revoke admin rights")

    def handle(self, email, remove=False, **options):
        user = User.objects.filter(email=email.lower()).first()
        if user is None:
            raise CommandError(f"No member with email {email}.")
        user.is_staff = user.is_superuser = not remove
        user.save(update_fields=["is_staff", "is_superuser"])
        state = "no longer an admin" if remove else "now an admin"
        self.stdout.write(self.style.SUCCESS(f"{user} is {state}."))
