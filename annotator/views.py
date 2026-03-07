from __future__ import annotations

import csv
import json
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Annotation, DatasetConfig, TokenAssignment, User
from .segmenter import TAG_UZ
from .services import (
    annotation_rows_for_export,
    generate_assignments,
    get_active_dataset,
    get_segmenter,
    get_user_assignments,
    load_words_from_dataset,
    refresh_user_stats,
    update_dataset_token_count,
)


APP_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = APP_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def _append_logs(dataset: DatasetConfig, payload: dict) -> None:
    base_name = f"dataset_{dataset.pk}"
    jsonl_path = OUTPUT_DIR / f"{base_name}_actions.jsonl"
    csv_path = OUTPUT_DIR / f"{base_name}_actions.csv"

    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    needs_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if needs_header:
            writer.writerow([
                "ts",
                "username",
                "token_index",
                "word",
                "action",
                "strategy",
                "segments",
                "tags",
                "subtypes",
                "codes",
            ])
        writer.writerow([
            payload["ts"],
            payload["username"],
            payload["token_index"],
            payload["word"],
            payload["action"],
            payload["strategy"],
            "|".join(payload["segments"]),
            "|".join(payload["tags"]),
            "|".join(payload["subtypes"]),
            "|".join(payload["codes"]),
        ])


def _get_or_prepare_dataset() -> DatasetConfig | None:
    dataset = get_active_dataset()
    if dataset and not dataset.assignments.exists():
        generate_assignments(dataset, reset=False)
    return dataset


def _assignment_payload(user: User, dataset: DatasetConfig, position: int | None) -> dict:
    assignments = get_user_assignments(user, dataset)
    if not assignments:
        return {"ok": False, "message": "Siz uchun assignment yo'q. Admin dataset yuklab, task yaratishi kerak."}

    if position is None:
        first_open = next((idx for idx, item in enumerate(assignments) if not item.is_completed), 0)
        position = first_open

    if position < 0 or position >= len(assignments):
        return {"ok": False, "message": "Tokenlar tugadi."}

    assignment = assignments[position]
    segmenter = get_segmenter(dataset)
    latest = Annotation.objects.filter(user=user, dataset=dataset, token_index=assignment.token_index).order_by("-created_at").first()

    existing = None
    if latest:
        existing = {
            "segments": latest.segments,
            "tags": latest.tags,
            "subtypes": latest.subtypes,
            "codes": latest.codes,
            "action": latest.action,
            "strategy": latest.strategy,
        }

    completed = sum(1 for item in assignments if item.is_completed)
    return {
        "ok": True,
        "position": position,
        "token_index": assignment.token_index,
        "total": len(assignments),
        "completed": completed,
        "word": assignment.word,
        "analysis": segmenter.segment(assignment.word, strategy="primary"),
        "existing": existing,
        "assignment_mode": dataset.assignment_mode,
        "tag_uz": TAG_UZ,
    }


def home(request):
    if request.user.is_authenticated:
        # Admin foydalanuvchilarni admin panelga yo'naltirish
        if request.user.is_superuser or request.user.role == "admin":
            return redirect("admin_dashboard")
        return redirect("profile")
    return redirect("login")


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def profile_view(request):
    # Admin foydalanuvchilar uchun ruxsat yo'q
    if request.user.is_superuser or request.user.role == "admin":
        return redirect("admin_dashboard")
    
    dataset = _get_or_prepare_dataset()
    assignments = []
    completed = 0
    if dataset:
        assignments = get_user_assignments(request.user, dataset)
        completed = sum(1 for item in assignments if item.is_completed)

    context = {
        "dataset": dataset,
        "assigned_count": len(assignments),
        "completed_count": completed,
        "recent_annotations": Annotation.objects.filter(user=request.user).order_by("-created_at")[:10],
    }
    return render(request, "annotator/profile.html", context)


@login_required
def annotate_view(request):
    # Admin foydalanuvchilar uchun ruxsat yo'q
    if request.user.is_superuser or request.user.role == "admin":
        return redirect("admin_dashboard")
    
    return render(request, "annotator/annotate.html")


@login_required
def statistics_view(request):
    dataset = get_active_dataset()
    
    # Admin uchun barcha annotatsiyalarni ko'rsatish
    if request.user.is_superuser or request.user.role == "admin":
        annotations = Annotation.objects.all().order_by("-created_at")[:50]
        total_annotations = Annotation.objects.count()
        assigned_count = TokenAssignment.objects.count()
        # Tugallangan = nechta token test qilingan (unique token_index + dataset)
        completed_count = Annotation.objects.values('dataset', 'token_index').distinct().count()
    else:
        # Oddiy foydalanuvchi uchun faqat o'z annotatsiyalari
        assignments = get_user_assignments(request.user, dataset) if dataset else []
        annotations = Annotation.objects.filter(user=request.user).order_by("-created_at")[:25]
        total_annotations = request.user.total_annotations
        assigned_count = len(assignments)
        # Tugallangan = user qilgan unique tokenlar soni
        completed_count = Annotation.objects.filter(user=request.user).values('dataset', 'token_index').distinct().count()
    
    remaining_count = max(0, assigned_count - completed_count)
    
    context = {
        "dataset": dataset,
        "assigned_count": assigned_count,
        "completed_count": completed_count,
        "remaining_count": remaining_count,
        "total_annotations": total_annotations,
        "annotations": annotations,
    }
    return render(request, "annotator/statistics.html", context)


@login_required
@require_POST
def reset_progress(request):
    """Foydalanuvchining barcha progressini qaytadan boshlash"""
    # Admin foydalanuvchilar uchun ruxsat yo'q
    if request.user.is_superuser or request.user.role == "admin":
        return redirect("admin_dashboard")
    
    # Barcha assignmentlarni qayta ochish
    TokenAssignment.objects.filter(user=request.user).update(is_completed=False, completed_at=None)
    
    messages.success(request, "Jarayon qaytadan boshlandi. Endi birinchi tokendan boshlab test qilishingiz mumkin!")
    return redirect("profile")


@login_required
@require_GET
def api_item(request):
    dataset = _get_or_prepare_dataset()
    if not dataset:
        return JsonResponse({"ok": False, "message": "Aktiv dataset yo'q. Admin CSV/TSV fayl yuklashi kerak."})

    position_param = request.GET.get("position")
    try:
        position = int(position_param) if position_param is not None else None
    except ValueError:
        return JsonResponse({"ok": False, "message": "Position xato."}, status=400)

    return JsonResponse(_assignment_payload(request.user, dataset, position))


@csrf_exempt
@login_required
@require_POST
def api_reanalyze(request):
    dataset = _get_or_prepare_dataset()
    if not dataset:
        return JsonResponse({"ok": False, "message": "Aktiv dataset yo'q."}, status=400)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "message": "JSON xato."}, status=400)

    segmenter = get_segmenter(dataset)
    word = (data.get("word") or "").strip()
    segments = data.get("segments") or []
    tags = data.get("tags") or []

    if segments:
        return JsonResponse({"ok": True, "analysis": segmenter.relabel(segments, tags), "mode": "manual"})
    return JsonResponse({"ok": True, "analysis": segmenter.segment(word, strategy="alternate"), "mode": "alternate"})


@csrf_exempt
@login_required
@require_POST
def api_save(request):
    dataset = _get_or_prepare_dataset()
    if not dataset:
        return JsonResponse({"ok": False, "message": "Aktiv dataset yo'q."}, status=400)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "message": "JSON xato."}, status=400)

    try:
        token_index = int(data.get("token_index"))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "message": "token_index xato."}, status=400)

    word = (data.get("word") or "").strip()
    action = (data.get("action") or "save").strip().lower()
    strategy = (data.get("strategy") or "primary").strip().lower()
    segments = data.get("segments") or []
    tags = data.get("tags") or []

    if action not in {"save", "delete"}:
        return JsonResponse({"ok": False, "message": "Action xato."}, status=400)

    assignment = TokenAssignment.objects.filter(user=request.user, dataset=dataset, token_index=token_index).first()
    if not assignment:
        return JsonResponse({"ok": False, "message": "Bu token sizga biriktirilmagan."}, status=403)

    relabeled = get_segmenter(dataset).relabel(segments, tags)
    had_previous = Annotation.objects.filter(user=request.user, dataset=dataset, token_index=token_index).exists()
    final_action = "update" if had_previous and action == "save" else action

    annotation = Annotation.objects.create(
        dataset=dataset,
        user=request.user,
        token_index=token_index,
        word=word,
        action=final_action,
        strategy=strategy,
        segments=relabeled["segments"],
        tags=relabeled["tags"],
        subtypes=relabeled["subtypes"],
        codes=relabeled["codes"],
    )

    assignment.is_completed = True
    assignment.completed_at = timezone.now()
    assignment.save(update_fields=["is_completed", "completed_at"])

    refresh_user_stats(request.user)

    payload = {
        "ts": timezone.now().isoformat(timespec="seconds"),
        "id": annotation.id,
        "username": request.user.username,
        "token_index": token_index,
        "word": word,
        "action": final_action,
        "strategy": strategy,
        "segments": relabeled["segments"],
        "tags": relabeled["tags"],
        "subtypes": relabeled["subtypes"],
        "codes": relabeled["codes"],
    }
    _append_logs(dataset, payload)

    return JsonResponse({"ok": True, "message": f"{final_action.upper()} saqlandi.", "saved": payload})


def _export_csv(rows: list[dict], filename: str) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(["id", "username", "token_index", "word", "action", "strategy", "segments", "tags", "subtypes", "codes", "created_at"])
    for row in rows:
        writer.writerow([
            row["id"],
            row["username"],
            row["token_index"],
            row["word"],
            row["action"],
            row["strategy"],
            "|".join(row["segments"]),
            "|".join(row["tags"]),
            "|".join(row["subtypes"]),
            "|".join(row["codes"]),
            row["created_at"],
        ])
    return response


def _export_jsonl(rows: list[dict], filename: str) -> HttpResponse:
    response = HttpResponse(content_type="application/x-ndjson; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    for row in rows:
        response.write(json.dumps(row, ensure_ascii=False) + "\n")
    return response


@login_required
def export_my_results(request, fmt: str):
    rows = annotation_rows_for_export(Annotation.objects.filter(user=request.user).select_related("user"))
    filename = f"{request.user.username}_annotations.{ 'jsonl' if fmt == 'jsonl' else 'csv' }"
    if fmt == "jsonl":
        return _export_jsonl(rows, filename)
    return _export_csv(rows, filename)


@user_passes_test(lambda u: u.is_superuser or getattr(u, "role", "") == "admin")
def export_admin_results(request, scope: str, fmt: str, user_id: int | None = None):
    queryset = Annotation.objects.select_related("user")
    if scope == "user" and user_id is not None:
        queryset = queryset.filter(user_id=user_id)
    rows = annotation_rows_for_export(queryset)
    suffix = f"user_{user_id}" if scope == "user" and user_id is not None else "all"
    filename = f"admin_{suffix}.{ 'jsonl' if fmt == 'jsonl' else 'csv' }"

    if fmt == "jsonl":
        return _export_jsonl(rows, filename)
    return _export_csv(rows, filename)

    if fmt == "jsonl":
        return _export_jsonl(rows, filename)
    return _export_csv(rows, filename)


@user_passes_test(lambda u: u.is_superuser or getattr(u, "role", "") == "admin")
def admin_dashboard(request):
    """Maxsus admin panel - faqat admin va superuser uchun"""
    
    # Dataset yaratish
    if request.method == "POST" and "create_dataset" in request.POST:
        name = request.POST.get("name", "").strip()
        tokens_file = request.FILES.get("tokens_file")
        suffix_file = request.FILES.get("suffix_file")
        assignment_mode = request.POST.get("assignment_mode", "shared")
        
        if name and tokens_file and suffix_file:
            dataset = DatasetConfig.objects.create(
                name=name,
                tokens_file=tokens_file,
                suffix_file=suffix_file,
                assignment_mode=assignment_mode,
                is_active=False
            )
            update_dataset_token_count(dataset)
            messages.success(request, f"Dataset '{name}' muvaffaqiyatli yaratildi!")
            return redirect("admin_dashboard")
        else:
            messages.error(request, "Barcha maydonlarni to'ldiring.")
    
    # Dataset aktivlashtirish
    if request.method == "POST" and "activate_dataset" in request.POST:
        dataset_id = request.POST.get("dataset_id")
        if dataset_id:
            DatasetConfig.objects.update(is_active=False)
            dataset = DatasetConfig.objects.filter(pk=dataset_id).first()
            if dataset:
                dataset.is_active = True
                dataset.save()
                messages.success(request, f"Dataset '{dataset.name}' aktivlashtirildi!")
        return redirect("admin_dashboard")
    
    # Assignment yaratish
    if request.method == "POST" and "generate_assignments" in request.POST:
        dataset_id = request.POST.get("dataset_id")
        if dataset_id:
            dataset = DatasetConfig.objects.filter(pk=dataset_id).first()
            if dataset:
                update_dataset_token_count(dataset)
                count = generate_assignments(dataset, reset=True)
                messages.success(request, f"Muvaffaqiyatli! {count} ta assignment yaratildi.")
            else:
                messages.error(request, "Dataset topilmadi.")
        return redirect("admin_dashboard")
    
    # Dataset tahrirlash (rejim o'zgartirish)
    if request.method == "POST" and "update_dataset" in request.POST:
        dataset_id = request.POST.get("dataset_id")
        new_mode = request.POST.get("new_assignment_mode")
        if dataset_id and new_mode:
            dataset = DatasetConfig.objects.filter(pk=dataset_id).first()
            if dataset:
                old_mode = dataset.assignment_mode
                dataset.assignment_mode = new_mode
                dataset.save()
                update_dataset_token_count(dataset)
                count = generate_assignments(dataset, reset=True)
                messages.success(request, f"Dataset rejimi o'zgartirildi: {old_mode} → {new_mode}. {count} ta yangi assignment yaratildi.")
            else:
                messages.error(request, "Dataset topilmadi.")
        return redirect("admin_dashboard")
    
    # Assignmentlarni o'chirish
    if request.method == "POST" and "delete_assignments" in request.POST:
        dataset_id = request.POST.get("dataset_id")
        if dataset_id:
            dataset = DatasetConfig.objects.filter(pk=dataset_id).first()
            if dataset:
                count = dataset.assignments.count()
                dataset.assignments.all().delete()
                messages.success(request, f"{count} ta assignment o'chirildi.")
            else:
                messages.error(request, "Dataset topilmadi.")
        return redirect("admin_dashboard")
    
    # Dataset o'chirish
    if request.method == "POST" and "delete_dataset" in request.POST:
        dataset_id = request.POST.get("dataset_id")
        if dataset_id:
            dataset = DatasetConfig.objects.filter(pk=dataset_id).first()
            if dataset:
                dataset_name = dataset.name
                dataset.delete()
                messages.success(request, f"Dataset '{dataset_name}' o'chirildi.")
        return redirect("admin_dashboard")
    
    # Ma'lumotlar
    datasets = DatasetConfig.objects.all().order_by("-created_at")
    users = User.objects.filter(role="annotator").order_by("-total_annotations")
    active_dataset = get_active_dataset()
    
    # Statistika
    total_annotations = Annotation.objects.count()
    total_completed = TokenAssignment.objects.filter(is_completed=True).count()
    total_pending = TokenAssignment.objects.filter(is_completed=False).count()
    
    context = {
        "datasets": datasets,
        "users": users,
        "active_dataset": active_dataset,
        "total_annotations": total_annotations,
        "total_completed": total_completed,
        "total_pending": total_pending,
    }
    
    return render(request, "annotator/admin_dashboard.html", context)

    return _export_csv(rows, filename)
