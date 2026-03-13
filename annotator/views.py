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
from .segmenter import TAG_UZ, dotted_code_for_tag, normalize_tag
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

ACTION_CSV_HEADERS = [
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
    "new_codes",
    "comment",
]


def _derive_new_codes(tags: list[str]) -> list[str]:
    return [dotted_code_for_tag(normalize_tag(tag)) for tag in (tags or [])]


def _upgrade_action_csv_if_needed(csv_path: Path, jsonl_path: Path) -> None:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return

    with csv_path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.reader(f)
        existing_rows = list(reader)

    if not existing_rows:
        return

    current_header = existing_rows[0]
    if current_header == ACTION_CSV_HEADERS:
        return

    rebuilt_rows = [ACTION_CSV_HEADERS]
    if jsonl_path.exists():
        with jsonl_path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                rebuilt_rows.append([
                    payload.get("ts", ""),
                    payload.get("username", ""),
                    payload.get("token_index", ""),
                    payload.get("word", ""),
                    payload.get("action", ""),
                    payload.get("strategy", ""),
                    "|".join(payload.get("segments", [])),
                    "|".join(payload.get("tags", [])),
                    "|".join(payload.get("subtypes", [])),
                    "|".join(payload.get("codes", [])),
                    "|".join(payload.get("new_codes") or _derive_new_codes(payload.get("tags", []))),
                    payload.get("comment", ""),
                ])
    else:
        for row in existing_rows[1:]:
            padded = list(row) + [""] * max(0, 12 - len(row))
            tags = padded[7].split("|") if padded[7] else []
            rebuilt_rows.append([
                padded[0],
                padded[1],
                padded[2],
                padded[3],
                padded[4],
                padded[5],
                padded[6],
                padded[7],
                padded[8],
                padded[9],
                "|".join(_derive_new_codes(tags)),
                padded[10] if len(padded) > 10 else "",
            ])

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rebuilt_rows)


def _append_logs(dataset: DatasetConfig, payload: dict) -> None:
    base_name = f"dataset_{dataset.pk}"
    jsonl_path = OUTPUT_DIR / f"{base_name}_actions.jsonl"
    csv_path = OUTPUT_DIR / f"{base_name}_actions.csv"

    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    _upgrade_action_csv_if_needed(csv_path, jsonl_path)
    needs_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if needs_header:
            writer.writerow(ACTION_CSV_HEADERS)
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
            "|".join(payload.get("new_codes", [])),
            payload.get("comment", ""),
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
    analysis = segmenter.segment(assignment.word, strategy="primary")
    latest = Annotation.objects.filter(user=user, dataset=dataset, token_index=assignment.token_index).order_by("-created_at").first()

    existing = None
    if latest:
        relabeled_existing = segmenter.relabel(latest.segments, latest.tags)
        existing = {
            "segments": relabeled_existing["segments"],
            "tags": relabeled_existing["tags"],
            "subtypes": relabeled_existing["subtypes"],
            "codes": relabeled_existing["codes"],
            "new_codes": relabeled_existing["new_codes"],
            "action": latest.action,
            "strategy": latest.strategy,
        }

        latest_is_auto_root = latest.strategy in {"primary", "alternate"} and (latest.tags == ["ROOT"] or len(latest.segments) <= 1)
        analysis_is_richer = len(analysis.get("segments", [])) > len(latest.segments or [])
        if latest_is_auto_root and analysis_is_richer:
            existing = None

    completed = sum(1 for item in assignments if item.is_completed)
    return {
        "ok": True,
        "position": position,
        "token_index": assignment.token_index,
        "total": len(assignments),
        "completed": completed,
        "word": assignment.word,
        "analysis": analysis,
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
    comment = (data.get("comment") or "").strip()
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
        assignment=assignment,
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
        "new_codes": relabeled["new_codes"],
        "comment": comment,
    }
    _append_logs(dataset, payload)

    return JsonResponse({"ok": True, "message": f"{final_action.upper()} saqlandi.", "saved": payload})


def _export_csv(rows: list[dict], filename: str) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(["id", "username", "token_index", "word", "action", "strategy", "segments", "tags", "subtypes", "codes", "new_codes", "comment", "created_at"])
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
            "|".join(row.get("new_codes", [])),
            row.get("comment", ""),
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
                assignment_count = dataset.assignments.count()
                annotation_count = dataset.annotations.count()
                
                # Avval annotationlarni o'chirish
                dataset.annotations.all().delete()
                
                # Keyin assignmentlarni o'chirish
                dataset.assignments.all().delete()
                
                messages.success(request, f"{assignment_count} ta assignment va {annotation_count} ta annotation o'chirildi.")
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


@login_required
def token_review_list(request):
    """Barcha tokenlar va ularning annotation'lari"""
    dataset = get_active_dataset()
    if not dataset:
        messages.error(request, "Aktiv dataset yo'q.")
        return redirect("home")
    
    # Admin uchun barcha tokenlar, oddiy user uchun faqat o'ziniki
    if request.user.is_superuser or request.user.role == "admin":
        assignments = TokenAssignment.objects.filter(dataset=dataset).select_related("user").order_by("token_index")
    else:
        assignments = TokenAssignment.objects.filter(dataset=dataset, user=request.user).order_by("token_index")
    
    # Har bir token uchun annotation sonini hisoblash
    token_data = []
    for assignment in assignments:
        annotation_count = Annotation.objects.filter(
            dataset=dataset,
            token_index=assignment.token_index,
            user=assignment.user
        ).count()
        
        latest_annotation = Annotation.objects.filter(
            dataset=dataset,
            token_index=assignment.token_index,
            user=assignment.user
        ).order_by("-created_at").first()
        
        token_data.append({
            "assignment": assignment,
            "annotation_count": annotation_count,
            "latest_annotation": latest_annotation,
        })
    
    context = {
        "dataset": dataset,
        "token_data": token_data,
    }
    return render(request, "annotator/token_review_list.html", context)


@login_required
def token_detail(request, token_index: int):
    """Bitta token uchun barcha annotation'lar va tahrirlash"""
    dataset = get_active_dataset()
    if not dataset:
        messages.error(request, "Aktiv dataset yo'q.")
        return redirect("home")
    
    # Admin uchun barcha user'lar, oddiy user uchun faqat o'zi
    if request.user.is_superuser or request.user.role == "admin":
        assignments = TokenAssignment.objects.filter(
            dataset=dataset,
            token_index=token_index
        ).select_related("user")
    else:
        assignments = TokenAssignment.objects.filter(
            dataset=dataset,
            token_index=token_index,
            user=request.user
        ).select_related("user")
    
    if not assignments.exists():
        messages.error(request, "Token topilmadi.")
        return redirect("token_review_list")
    
    # Har bir user uchun annotation'larni olish
    token_annotations = []
    for assignment in assignments:
        annotations = Annotation.objects.filter(
            dataset=dataset,
            token_index=token_index,
            user=assignment.user
        ).order_by("-created_at")
        
        token_annotations.append({
            "assignment": assignment,
            "annotations": annotations,
        })
    
    context = {
        "dataset": dataset,
        "token_index": token_index,
        "word": assignments.first().word,
        "token_annotations": token_annotations,
    }
    return render(request, "annotator/token_detail.html", context)


@login_required
@require_POST
def annotation_edit(request, annotation_id: int):
    """Annotation tahrirlash"""
    annotation = Annotation.objects.filter(id=annotation_id).first()
    
    if not annotation:
        messages.error(request, "Annotation topilmadi.")
        return redirect("token_review_list")
    
    # Faqat o'z annotation'ini yoki admin tahrirlashi mumkin
    if annotation.user != request.user and not (request.user.is_superuser or request.user.role == "admin"):
        messages.error(request, "Siz bu annotation'ni tahrirlay olmaysiz.")
        return redirect("token_review_list")
    
    try:
        segments = json.loads(request.POST.get("segments", "[]"))
        tags = json.loads(request.POST.get("tags", "[]"))
        subtypes = json.loads(request.POST.get("subtypes", "[]"))
        codes = json.loads(request.POST.get("codes", "[]"))
        
        annotation.segments = segments
        annotation.tags = tags
        annotation.subtypes = subtypes
        annotation.codes = codes
        annotation.action = "update"
        annotation.save()
        
        messages.success(request, "Annotation tahrirlandi!")
    except json.JSONDecodeError:
        messages.error(request, "JSON ma'lumotlar xato.")
    
    return redirect("token_detail", token_index=annotation.token_index)


@login_required
@require_POST
def annotation_delete(request, annotation_id: int):
    """Annotation o'chirish"""
    annotation = Annotation.objects.filter(id=annotation_id).first()
    
    if not annotation:
        messages.error(request, "Annotation topilmadi.")
        return redirect("token_review_list")
    
    # Faqat o'z annotation'ini yoki admin o'chirishi mumkin
    if annotation.user != request.user and not (request.user.is_superuser or request.user.role == "admin"):
        messages.error(request, "Siz bu annotation'ni o'chira olmaysiz.")
        return redirect("token_review_list")
    
    token_index = annotation.token_index
    annotation.delete()
    messages.success(request, "Annotation o'chirildi!")
    
    return redirect("token_detail", token_index=token_index)
