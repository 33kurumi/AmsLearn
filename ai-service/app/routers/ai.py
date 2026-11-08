"""AI 能力路由：AI1~AI11。"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from .. import service
from ..config import settings
from ..schemas import (
    ClassAnalysisRequest,
    ClassAnalysisResponse,
    ConfigExtractRequest,
    ConfigExtractResponse,
    DiagnoseQuestionsRequest,
    GateCheckRequest,
    GateCheckResponse,
    GradeRequest,
    GradeResponse,
    HealthResponse,
    HintRequest,
    HintResponse,
    IntentRequest,
    IntentResponse,
    PlanRequest,
    PlanResponse,
    PracticeQuestionsRequest,
    PracticeQuestionsResponse,
    QARequest,
    QAResponse,
    QuestionsResponse,
    RetrieveRequest,
    RetrieveResponse,
    VisionExtractResponse,
)

router = APIRouter(tags=["ai"])


@router.get("/health", response_model=HealthResponse, summary="AI1 健康与索引统计")
def health() -> HealthResponse:
    return service.health()


@router.post("/qa", response_model=QAResponse, summary="AI2 答疑（W1）")
def qa(req: QARequest) -> QAResponse:
    try:
        return service.qa(req)
    except Exception as exc:  # noqa: BLE001 - 兜底，避免 500
        raise HTTPException(status_code=500, detail="答疑失败：" + str(exc)) from exc


@router.post(
    "/qa/gate/check",
    response_model=GateCheckResponse,
    summary="v1.3 前置自测判分 + 通过后三步教学",
)
def gate_check(req: GateCheckRequest) -> GateCheckResponse:
    try:
        return service.gate_check(req)
    except Exception as exc:  # noqa: BLE001 - 兜底，避免 500
        raise HTTPException(status_code=500, detail="前置自测判分失败：" + str(exc)) from exc


@router.post("/intent", response_model=IntentResponse, summary="AI3 意图识别（W0）")
def intent(req: IntentRequest) -> IntentResponse:
    return service.detect_intent(req)


@router.post("/retrieve", response_model=RetrieveResponse, summary="AI4 知识库检索")
def retrieve(req: RetrieveRequest) -> RetrieveResponse:
    return service.retrieve(req)


@router.post("/diagnose/questions", response_model=QuestionsResponse, summary="AI5 诊断出题（W2）")
def diagnose_questions(req: DiagnoseQuestionsRequest) -> QuestionsResponse:
    return service.diagnose_questions(req)


@router.post("/diagnose/grade", response_model=GradeResponse, summary="AI6 诊断批改")
def diagnose_grade(req: GradeRequest) -> GradeResponse:
    return service.grade(req)


@router.post("/practice/questions", response_model=PracticeQuestionsResponse, summary="AI7 分层练习出题（W3）")
def practice_questions(req: PracticeQuestionsRequest) -> PracticeQuestionsResponse:
    return service.practice_questions(req)


@router.post("/practice/hint", response_model=HintResponse, summary="AI8 练习思路提示")
def practice_hint(req: HintRequest) -> HintResponse:
    return service.practice_hint(req)


@router.post("/plan", response_model=PlanResponse, summary="AI9 学习计划生成（W3）")
def plan(req: PlanRequest) -> PlanResponse:
    return service.plan(req)


@router.post("/class-analysis", response_model=ClassAnalysisResponse, summary="AI10 班级学情建议（W4-B）")
def class_analysis(req: ClassAnalysisRequest) -> ClassAnalysisResponse:
    return service.class_analysis(req)


@router.post("/config/extract", response_model=ConfigExtractResponse, summary="AI11 自然语言配置抽取（W4-A）")
def config_extract(req: ConfigExtractRequest) -> ConfigExtractResponse:
    return service.config_extract(req)


# --------------------------------------------------------------------------
# v1.3 AI17 /vision/extract：讲义/题目图片 OCR（契约 §1.2，HTTP 恒 200）
# --------------------------------------------------------------------------
MAX_VISION_BYTES = 5 * 1024 * 1024


@router.post(
    "/vision/extract",
    response_model=VisionExtractResponse,
    summary="v1.3 图片识别（OCR，课件/题目截图转文字）",
)
async def vision_extract(file: UploadFile = File(...)) -> VisionExtractResponse:
    from .. import vision

    provider = settings.vision_provider_name
    model = settings.vision_model
    if not settings.vision_ready:
        return VisionExtractResponse(
            ok=False,
            text="",
            model=model,
            provider=provider,
            message=vision.NOT_CONFIGURED_MESSAGE,
        )
    try:
        data = await file.read()
        if len(data) > MAX_VISION_BYTES:
            return VisionExtractResponse(
                ok=False,
                text="",
                model=model,
                provider=provider,
                message="图片过大：请上传不超过 5MB 的图片。",
            )
        content_type = (file.content_type or "").split(";")[0].strip().lower()
        if content_type not in vision.ALLOWED_IMAGE_TYPES:
            return VisionExtractResponse(
                ok=False,
                text="",
                model=model,
                provider=provider,
                message="仅支持 png/jpeg/webp/gif 格式的图片。",
            )
        text = vision.client.extract(data, content_type)
        return VisionExtractResponse(
            ok=True, text=text, model=model, provider=provider, message=None
        )
    except vision.VisionError as exc:
        return VisionExtractResponse(
            ok=False, text="", model=model, provider=provider, message=str(exc)
        )
    except Exception as exc:  # noqa: BLE001 - 契约要求恒 200，绝不抛 500
        return VisionExtractResponse(
            ok=False,
            text="",
            model=model,
            provider=provider,
            message=vision.FAILED_MESSAGE,
        )
