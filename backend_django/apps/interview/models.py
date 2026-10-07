import uuid

from django.db import models

from apps.common.models import UserOwnedModel


def session_id():
    return f"int_{uuid.uuid4().hex}"


def turn_id():
    return f"itr_{uuid.uuid4().hex}"


def corpus_id():
    return f"icp_{uuid.uuid4().hex}"


class InterviewProfile(UserOwnedModel):
    """One per user: the resume and the target job description, each split by AI into practice material."""

    resume_text = models.TextField(blank=True)
    resume_modules = models.JSONField(default=list, blank=True)
    resume_updated_at = models.DateTimeField(null=True, blank=True)
    jd_text = models.TextField(blank=True)
    jd_summary = models.JSONField(default=dict, blank=True)
    jd_updated_at = models.DateTimeField(null=True, blank=True)
    # The candidate's own order for the knowledge library: {"tags": [direction, ...], "topics": {direction: [topic, ...]}}.
    # Names listed come first in that order; anything not listed keeps the default order (bank order, then own as added).
    knowledge_layout = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user"], name="interview_one_profile_per_user")]


class InterviewCorpusEntry(UserOwnedModel):
    """The interview counterpart of the IELTS speaking corpora: a question plus "my answer" and an AI reference."""

    class Kind(models.TextChoices):
        SELF_INTRO = "self_intro", "自我介绍"
        PROJECT = "project", "项目讲述"
        PROJECT_FOLLOWUP = "project_followup", "项目追问"
        KNOWLEDGE = "knowledge", "知识点"
        AWARD = "award", "奖项"
        JD_QUESTION = "jd_question", "岗位题"
        REVERSE_QUESTION = "reverse_question", "反问"
        JD = "jd", "JD"

    class Source(models.TextChoices):
        CURATED = "curated", "精选题库"
        RESUME = "resume", "简历"
        JD = "jd", "岗位描述"
        CUSTOM = "custom", "自定义"
        PRACTICE = "practice", "练习"

    entry_id = models.CharField(max_length=40, unique=True, default=corpus_id)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    group = models.CharField(max_length=80, blank=True)
    title = models.CharField(max_length=200, blank=True)
    question = models.TextField()
    corpus_text = models.TextField(blank=True)
    ai_draft = models.TextField(blank=True)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.CUSTOM)
    # Stable identity across regenerations (curated question id, resume module key, hashed JD question),
    # so re-splitting a resume refreshes the AI draft without touching the user's own answer.
    source_key = models.CharField(max_length=160, blank=True)
    parent = models.ForeignKey("self", related_name="children", null=True, blank=True, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["kind", "group", "order", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["user", "source_key"], condition=~models.Q(source_key=""),
                                    name="interview_corpus_unique_source_key"),
        ]
        indexes = [models.Index(fields=["user", "kind", "order"], name="interview_corpus_kind_idx")]


class InterviewSession(UserOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ABORTED = "aborted", "Aborted"

    class Part(models.TextChoices):
        FULL = "full", "完整面试"
        PROJECT = "project", "项目"
        KNOWLEDGE = "knowledge", "知识点"
        REVERSE = "reverse", "反问"

    class Intensity(models.TextChoices):
        STANDARD = "standard", "标准模式"
        PRESSURE = "pressure", "追问压力"

    public_id = models.CharField(max_length=40, unique=True, default=session_id)
    mode = models.CharField(max_length=16, choices=[("general", "General"), ("custom", "Custom"), ("studio", "Studio")])
    part = models.CharField(max_length=16, choices=Part.choices, default=Part.KNOWLEDGE)
    intensity = models.CharField(max_length=16, choices=Intensity.choices, default=Intensity.STANDARD)
    plan = models.JSONField(default=list, blank=True)
    score = models.JSONField(default=dict, blank=True)
    title = models.CharField(max_length=160)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    report = models.JSONField(default=dict, blank=True)
    # Request lease prevents inserting a follow-up while another answer advances.
    ai_busy_since = models.DateTimeField(null=True, blank=True)
    ai_busy_kind = models.CharField(max_length=32, blank=True)
    ai_busy_token = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["user", "status", "created_at"])]


class InterviewTurn(UserOwnedModel):
    public_id = models.CharField(max_length=40, unique=True, default=turn_id)
    session = models.ForeignKey(InterviewSession, related_name="turns", on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=16, choices=[("main", "Main"), ("follow_up", "Follow up")], default="main")
    parent = models.OneToOneField("self", related_name="follow_up", null=True, blank=True, on_delete=models.CASCADE)
    question_id = models.CharField(max_length=80, blank=True)
    stage = models.CharField(max_length=16, blank=True)
    corpus_entry_id = models.CharField(max_length=40, blank=True)
    answer_source = models.CharField(max_length=8, choices=[("typed", "Typed"), ("voice", "Voice")], default="typed")
    audio_path = models.CharField(max_length=255, blank=True)
    prompt = models.TextField()
    category = models.CharField(max_length=32, blank=True)
    difficulty = models.CharField(max_length=16, default="intermediate")
    source = models.CharField(max_length=32, default="curated")
    answer = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=[("pending", "Pending"), ("completed", "Completed"), ("skipped", "Skipped")], default="pending")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["order", "pk"]
        constraints = [models.UniqueConstraint(fields=["session", "order"], name="interview_unique_turn_order")]


def thread_id():
    return f"iat_{uuid.uuid4().hex}"


def message_id():
    return f"iam_{uuid.uuid4().hex}"


class InterviewAssistantThread(UserOwnedModel):
    """One AI 助手 conversation, listed like a chat history."""

    thread_id = models.CharField(max_length=40, unique=True, default=thread_id)
    title = models.CharField(max_length=80, blank=True)
    # interview (the interview corpus) or ielts (the IELTS speaking corpora): each mode keeps its own chats.
    domain = models.CharField(max_length=16, default="interview")

    class Meta:
        indexes = [models.Index(fields=["user", "updated_at"])]


class InterviewAssistantMessage(models.Model):
    """A message in a thread; assistant messages keep what they wrote into the library and the agent trace."""

    class Role(models.TextChoices):
        USER = "user", "用户"
        ASSISTANT = "assistant", "助手"

    message_id = models.CharField(max_length=40, unique=True, default=message_id)
    thread = models.ForeignKey(InterviewAssistantThread, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=12, choices=Role.choices)
    content = models.TextField()
    mode = models.CharField(max_length=16, blank=True)
    applied = models.JSONField(default=list, blank=True)
    steps = models.JSONField(default=list, blank=True)
    # How to reverse what this reply wrote (created / updated / deleted rows), and whether that has been done.
    undo = models.JSONField(default=list, blank=True)
    undone = models.BooleanField(default=False)
    # Files sent with a user message: name and kind only (the files themselves are not kept).
    attachments = models.JSONField(default=list, blank=True)
    model = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
