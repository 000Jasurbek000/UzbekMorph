from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from annotator.models import DatasetConfig
from annotator.services import generate_assignments, update_dataset_token_count


class Command(BaseCommand):
    help = "Mavjud top_ge_500.tsv va suffix_lexicon.tsv asosida aktiv dataset yaratadi"

    def handle(self, *args, **options):
        root = Path(__file__).resolve().parents[4]
        token_path = root / "top_ge_500.tsv"
        suffix_path = root / "suffix_lexicon.tsv"

        if not token_path.exists() or not suffix_path.exists():
            raise CommandError("top_ge_500.tsv yoki suffix_lexicon.tsv topilmadi")

        dataset = DatasetConfig(name="Default dataset", assignment_mode="individual", is_active=True)
        with token_path.open("rb") as token_file:
            dataset.tokens_file.save(token_path.name, File(token_file), save=False)
        with suffix_path.open("rb") as suffix_file:
            dataset.suffix_file.save(suffix_path.name, File(suffix_file), save=False)
        dataset.save()
        update_dataset_token_count(dataset)
        count = generate_assignments(dataset, reset=True)
        self.stdout.write(self.style.SUCCESS(f"Dataset yaratildi. Assignmentlar: {count}"))
