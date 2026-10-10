"""Human rubrics per task: 1-5 scales with Chinese anchors at 1, 3 and 5.

Machine metrics cannot judge prose quality, whether a figure is the right one,
errors outside the reference key points, teaching correctness for a student, or
whether an output is publishable. These rubrics cover exactly that.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Dimension:
    id: str
    name: str
    question: str
    anchors: tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class Rubric:
    task: str
    title: str
    dimensions: tuple[Dimension, ...]
    human_only: str


RUBRICS: dict[str, Rubric] = {
    "t1": Rubric(
        task="t1",
        title="长视频 → 图文公众号文章",
        dimensions=(
            Dimension(
                "faithfulness",
                "忠实度",
                "文章里的事实、人名、数字是否和视频一致？有没有编造？",
                (
                    "多处与视频不符或明显编造",
                    "大体忠实，有 1–2 处小错误或含糊",
                    "全部与视频一致，没有编造",
                ),
            ),
            Dimension(
                "structure",
                "结构与可读性",
                "像不像一篇成品文章：标题、引言、要点、小节是否清楚、连贯？",
                (
                    "像转写稿堆砌，结构混乱",
                    "有标题、要点和小节，但衔接生硬",
                    "标题吸引人，层次清楚，读起来像成品",
                ),
            ),
            Dimension(
                "images",
                "配图与图注",
                "配图是否选在关键画面？图注是否准确说明画面并服务正文？",
                (
                    "配图无关、重复或近乎空白，图注只有时间",
                    "多数配图相关，图注一般",
                    "每张图都在关键画面，图注准确",
                ),
            ),
            Dimension(
                "publishable",
                "可发布程度",
                "要改多久才能发公众号？",
                ("需要重写", "改 30 分钟以上能发", "改 10 分钟以内能发"),
            ),
        ),
        human_only="文笔与可读性、配图是否选对、参考要点之外的事实错误、是否愿意发布",
    ),
    "t2a": Rubric(
        task="t2a",
        title="讲解视频分镜（主题 → 脚本 → HTML）",
        dimensions=(
            Dimension(
                "clarity",
                "讲解清晰度",
                "看完能否真正理解这个概念？是从原理推出结论，还是只罗列结论？",
                ("看不懂或只罗列结论", "能懂个大概，推导有跳跃", "从原理一步步推出结论，清楚"),
            ),
            Dimension(
                "faithfulness",
                "忠实与准确",
                "内容、数字、术语是否与素材一致且正确？",
                ("有明显错误或编造", "基本正确，有小瑕疵", "完全正确，数字和术语准确"),
            ),
            Dimension(
                "producibility",
                "可制作性",
                "分镜、画面描述、字幕能否直接做成动画？节奏是否合适？",
                ("无法直接制作", "需要较多补充和调整", "可以直接照着做"),
            ),
        ),
        human_only="讲解是否真的讲清楚、画面是否有表现力、节奏是否舒服",
    ),
    "t2b": Rubric(
        task="t2b",
        title="播客 / 片段点评",
        dimensions=(
            Dimension(
                "accuracy",
                "概括准确",
                "概括是否抓住了片段的核心内容？",
                ("偏离或遗漏核心", "抓住部分核心", "准确完整"),
            ),
            Dimension(
                "grounding",
                "观点有据",
                "每条观点是否确实出现在片段里，时间点是否对得上？",
                ("多条找不到出处", "大部分能对上", "全部能对上"),
            ),
            Dimension(
                "insight",
                "有用性",
                "点评是否有信息量，值得读者花时间？",
                ("空洞", "一般", "有信息量和洞察"),
            ),
        ),
        human_only="观点是否真的出自说话人、语气是否被曲解、是否值得一读",
    ),
    "t3": Rubric(
        task="t3",
        title="老师录屏 → 错题、学习笔记、教学视频",
        dimensions=(
            Dimension(
                "questions",
                "错题提取",
                "题目是否抽全、题干和正确答案是否准确？",
                ("漏题或答案错误", "大部分正确，有遗漏或小错", "全部正确完整"),
            ),
            Dimension(
                "explanation",
                "讲解正确且适合学生",
                "常见错误分析和解题步骤是否正确、初中生能否看懂？",
                ("有错误或学生看不懂", "正确但不够清楚", "正确且清楚易懂"),
            ),
            Dimension(
                "notes",
                "笔记可用性",
                "笔记能否直接用来复习？配图是否有帮助？",
                ("不能用", "要修改后才能用", "可以直接用"),
            ),
            Dimension(
                "video",
                "教学视频脚本",
                "分镜和字幕能否做成一条对学生有用的讲解视频？",
                ("不能用", "要较多修改", "可以直接制作"),
            ),
        ),
        human_only="答案与讲解的正确性（教学责任）、是否适合这个学生、是否愿意给学生看",
    ),
}


def get_rubric(task: str) -> Rubric:
    try:
        return RUBRICS[task]
    except KeyError:
        raise ValueError(f"no rubric for task: {task}") from None
