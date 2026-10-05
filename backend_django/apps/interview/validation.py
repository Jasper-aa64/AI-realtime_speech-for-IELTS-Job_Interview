import shutil
import subprocess
import tempfile
import threading


class InterviewError(ValueError):
    def __init__(self, message, *, code="invalid_request", status=400):
        super().__init__(message)
        self.code = code
        self.status = status


# Field names the candidate can actually run into, shown in Chinese in validation messages.
FIELD_LABELS = {"answer": "回答", "resume_text": "简历文字", "job_description": "岗位描述", "question": "题目",
                "corpus_text": "我的答法", "title": "标题", "transcript": "转写稿"}


def text(value, name, limit, *, required=False):
    label = FIELD_LABELS.get(name, name)
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise InterviewError(f"{label}格式不正确")
    value = value.strip()
    if "\x00" in value or len(value) > limit:
        raise InterviewError(f"{label}超出长度限制（最多 {limit} 字）")
    if required and not value:
        raise InterviewError(f"请填写{label}")
    return value


def count(value, default=5):
    if value is None or value == "":
        return default
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise InterviewError("count must be an integer from 1 to 10")
    try:
        number = int(value)
    except (ValueError, TypeError):
        raise InterviewError("count must be an integer from 1 to 10") from None
    if not 1 <= number <= 10:
        raise InterviewError("count must be an integer from 1 to 10")
    return number


def custom_questions(values, *, source="user_custom"):
    if not isinstance(values, list) or not 1 <= len(values) <= 10:
        raise InterviewError("Provide between 1 and 10 questions")
    questions = []
    for value in values:
        item = {"prompt": value} if isinstance(value, str) else value
        if not isinstance(item, dict):
            raise InterviewError("Each question must be text or an object")
        questions.append({
            "prompt": text(item.get("prompt"), "question", 1500, required=True),
            "category": text(item.get("category", "projects"), "category", 32),
            "difficulty": text(item.get("difficulty", "intermediate"), "difficulty", 16),
            "source": source,
        })
    if len({q["prompt"] for q in questions}) != len(questions):
        raise InterviewError("Questions must not be duplicated")
    return questions


def extract_pdf(data):
    executable = shutil.which("pdftotext")
    if not executable:
        raise InterviewError("暂时无法解析 PDF，请直接粘贴简历文字。", code="pdf_unavailable")
    # Cap output while the process runs, rather than capturing arbitrarily
    # expanded compressed PDF text before validating its length. Stderr is
    # discarded, never accumulated or reflected to the caller.
    output = bytearray()
    too_large = threading.Event()
    with tempfile.TemporaryFile() as input_file:
        input_file.write(data)
        input_file.seek(0)
        try:
            process = subprocess.Popen([executable, "-f", "1", "-l", "20", "-", "-"],
                                       stdin=input_file, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            raise InterviewError("PDF 无法读取，请粘贴简历文字。", code="invalid_pdf") from None

        def read_output():
            try:
                while True:
                    chunk = process.stdout.read(4096)
                    if not chunk:
                        break
                    if len(output) + len(chunk) > 96000:
                        too_large.set()
                        process.kill()
                        break
                    output.extend(chunk)
            except (OSError, ValueError):
                pass

        reader = threading.Thread(target=read_output, name="interview-pdf-output", daemon=True)
        reader.start()
        timed_out = False
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            process.wait(timeout=2)
        finally:
            reader.join(timeout=2)
            process.stdout.close()
        if timed_out or reader.is_alive():
            raise InterviewError("PDF 解析超时，请粘贴简历文字。", code="invalid_pdf")
        if too_large.is_set():
            raise InterviewError("PDF 内容过长，请粘贴精简后的简历。", code="invalid_pdf")
        if process.returncode:
            raise InterviewError("PDF 无法读取，请使用未加密的文字版 PDF。", code="invalid_pdf")
    return output.decode("utf-8", errors="replace").strip()


def resume_input(resume_text, upload):
    content = text(resume_text, "resume_text", 24000)
    if upload is not None:
        if upload.size <= 0 or upload.size > 2 * 1024 * 1024:
            raise InterviewError("PDF 简历需要小于 2 MB。", code="invalid_pdf")
        data = upload.read(2 * 1024 * 1024 + 1)
        if not data.startswith(b"%PDF-") or len(data) > 2 * 1024 * 1024:
            raise InterviewError("请上传有效的 PDF 简历。", code="invalid_pdf")
        extracted = extract_pdf(data)
        if not extracted:
            raise InterviewError("PDF 里没有可读文字（可能是扫描件），请粘贴简历文字。", code="empty_pdf")
        content = text("\n\n".join(filter(None, (content, extracted))), "resume_text", 24000)
    return text(content, "resume_text", 24000, required=True)
