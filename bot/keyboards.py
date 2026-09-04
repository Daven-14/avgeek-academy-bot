"""Inline keyboard builders. Callback data stays well under Telegram's 64-byte limit."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.content_loader import Module, QuizItem


GOAL_CHOICES: tuple[tuple[str, str], ...] = (
    ("Curious flyer", "ob:curious"),
    ("Student pilot", "ob:student"),
    ("Engineer / avgeek", "ob:engineer"),
    ("Just browsing", "ob:browse"),
)


def onboarding_goals() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=cb)] for label, cb in GOAL_CHOICES
    ]
    return InlineKeyboardMarkup(rows)


def main_menu(*, daily_on: bool = False, streak: int = 0) -> InlineKeyboardMarkup:
    daily_label = "📅 Daily lesson: ON" if daily_on else "📅 Daily lesson: OFF"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("▶️ Continue learning", callback_data="cont")],
        [
            InlineKeyboardButton("🗺️ Learning path", callback_data="path"),
            InlineKeyboardButton("🧠 Review", callback_data="rev"),
        ],
        [InlineKeyboardButton("📚 Browse modules", callback_data="mods")],
        [
            InlineKeyboardButton("✈️ Random fact", callback_data="fact"),
            InlineKeyboardButton("📖 Glossary", callback_data="gl"),
        ],
        [
            InlineKeyboardButton("📊 Progress", callback_data="pr"),
            InlineKeyboardButton("🏅 Certificates", callback_data="certs"),
        ],
        [
            InlineKeyboardButton(daily_label, callback_data="daily:tog"),
            InlineKeyboardButton("💚 Tip (optional)", callback_data="pro"),
        ],
        [
            InlineKeyboardButton("⚖️ Legal", callback_data="legal"),
            InlineKeyboardButton("❓ Help", callback_data="h"),
        ],
    ]
    _ = streak
    return InlineKeyboardMarkup(rows)


def welcome_cta() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("▶️ Continue learning", callback_data="cont")],
            [InlineKeyboardButton("🗺️ Learning path", callback_data="path")],
            [InlineKeyboardButton("📚 Main menu", callback_data="m")],
        ]
    )


def modules_menu(
    modules: tuple[Module, ...], user_id: int
) -> InlineKeyboardMarkup:
    _ = user_id
    rows: list[list[InlineKeyboardButton]] = []
    for m in modules:
        label = f"{m.emoji} {m.title}"
        rows.append(
            [InlineKeyboardButton(label, callback_data=f"md:{m.id}")]
        )
    rows.append(
        [
            InlineKeyboardButton("🗺️ Path", callback_data="path"),
            InlineKeyboardButton("🏠 Main menu", callback_data="m"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def path_menu(
    modules: tuple[Module, ...],
    *,
    completed_ids: set[str],
    next_mod_id: str | None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for m in modules:
        done = m.id in completed_ids
        mark = "☑️" if done else "☐"
        here = " → You are here" if (next_mod_id and m.id == next_mod_id) else ""
        label = f"{mark} {m.emoji} {m.title}{here}"
        # Truncate if needed for Telegram button label (~64 visible is fine)
        if len(label) > 60:
            label = label[:57] + "…"
        rows.append([InlineKeyboardButton(label, callback_data=f"md:{m.id}")])
    if next_mod_id:
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    "▶️ Continue next module", callback_data=f"md:{next_mod_id}"
                )
            ],
        )
    rows.append(
        [
            InlineKeyboardButton("▶️ Continue lesson", callback_data="cont"),
            InlineKeyboardButton("🏠 Menu", callback_data="m"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def module_home(mod: Module, lessons_seen: int) -> InlineKeyboardMarkup:
    n = len(mod.lessons)
    label = "Start lessons" if lessons_seen == 0 else "Continue lessons"
    start_idx = min(lessons_seen, n - 1)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"📖 {label}", callback_data=f"l:{mod.id}:{start_idx}")],
            [InlineKeyboardButton("📝 Quiz me", callback_data=f"qz:{mod.id}")],
            [
                InlineKeyboardButton("🗺️ Path", callback_data="path"),
                InlineKeyboardButton("📚 All modules", callback_data="mods"),
            ],
            [InlineKeyboardButton("🏠 Menu", callback_data="m")],
        ]
    )


def upgrade_cta(module_title: str) -> InlineKeyboardMarkup:
    """Legacy callback target — content is free; keep a soft tip CTA."""
    _ = module_title
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📚 Open modules", callback_data="mods")],
            [InlineKeyboardButton("💚 Optional tip", callback_data="buy")],
            [InlineKeyboardButton("🏠 Menu", callback_data="m")],
        ]
    )


def pro_menu(*, is_premium: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not is_premium:
        rows.append(
            [InlineKeyboardButton("💚 Send optional tip (Stars)", callback_data="buy")]
        )
    rows.append([InlineKeyboardButton("🏠 Main menu", callback_data="m")])
    return InlineKeyboardMarkup(rows)


def lesson_nav(mod: Module, idx: int) -> InlineKeyboardMarkup:
    n = len(mod.lessons)
    row_nav: list[InlineKeyboardButton] = []
    if idx > 0:
        row_nav.append(
            InlineKeyboardButton("⬅️ Prev", callback_data=f"l:{mod.id}:{idx - 1}")
        )
    if idx < n - 1:
        row_nav.append(
            InlineKeyboardButton("Next ➡️", callback_data=f"l:{mod.id}:{idx + 1}")
        )
    else:
        row_nav.append(
            InlineKeyboardButton("📝 Take the quiz", callback_data=f"qz:{mod.id}")
        )

    extra: list[InlineKeyboardButton] = [
        InlineKeyboardButton("💡 Explain simpler", callback_data=f"e:{mod.id}:{idx}"),
    ]
    if idx < n - 1:
        extra.append(
            InlineKeyboardButton("📝 Quiz me", callback_data=f"qz:{mod.id}")
        )

    return InlineKeyboardMarkup(
        [
            row_nav,
            extra,
            [InlineKeyboardButton(f"⬅️ {mod.title}", callback_data=f"md:{mod.id}")],
        ]
    )


def simple_nav(mod: Module, idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "↩️ Back to lesson", callback_data=f"l:{mod.id}:{idx}"
                )
            ],
            (
                [
                    InlineKeyboardButton(
                        "Next ➡️", callback_data=f"l:{mod.id}:{idx + 1}"
                    )
                ]
                if idx < len(mod.lessons) - 1
                else [
                    InlineKeyboardButton(
                        "📝 Take the quiz", callback_data=f"qz:{mod.id}"
                    )
                ]
            ),
        ]
    )


def quiz_choices(mod_id: str, q_idx: int, item: QuizItem) -> InlineKeyboardMarkup:
    letters = "ABCD"
    rows = [
        [
            InlineKeyboardButton(
                f"{letters[i]}. {opt}",
                callback_data=f"qa:{mod_id}:{q_idx}:{i}",
            )
        ]
        for i, opt in enumerate(item.options)
    ]
    return InlineKeyboardMarkup(rows)


def quiz_next(mod_id: str, next_idx: int, last: bool) -> InlineKeyboardMarkup:
    if last:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🏁 See score", callback_data=f"qs:{mod_id}")],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Next question ➡️", callback_data=f"qn:{mod_id}:{next_idx}"
                )
            ]
        ]
    )


def quiz_done(mod_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔁 Retry quiz", callback_data=f"qz:{mod_id}")],
            [
                InlineKeyboardButton("📖 Lessons", callback_data=f"l:{mod_id}:0"),
                InlineKeyboardButton("⬅️ Module", callback_data=f"md:{mod_id}"),
            ],
            [
                InlineKeyboardButton("🗺️ Path", callback_data="path"),
                InlineKeyboardButton("🏠 Main menu", callback_data="m"),
            ],
        ]
    )


def after_fact() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✈️ Another fact", callback_data="fact")],
            [
                InlineKeyboardButton("📚 Modules", callback_data="mods"),
                InlineKeyboardButton("🏠 Menu", callback_data="m"),
            ],
        ]
    )


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠 Main menu", callback_data="m")]]
    )


def glossary_result(*, related_mod_id: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if related_mod_id:
        rows.append(
            [
                InlineKeyboardButton(
                    "📘 Related lesson", callback_data=f"md:{related_mod_id}"
                )
            ]
        )
    rows.append([InlineKeyboardButton("📚 Browse modules", callback_data="mods")])
    rows.append([InlineKeyboardButton("🏠 Main menu", callback_data="m")])
    return InlineKeyboardMarkup(rows)


def glossary_prompt() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📚 Browse modules", callback_data="mods")],
            [InlineKeyboardButton("🏠 Main menu", callback_data="m")],
        ]
    )


def certs_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📚 Modules", callback_data="mods")],
            [InlineKeyboardButton("🏠 Main menu", callback_data="m")],
        ]
    )


def review_choices(mod_id: str, q_idx: int, item: QuizItem) -> InlineKeyboardMarkup:
    letters = "ABCD"
    rows = [
        [
            InlineKeyboardButton(
                f"{letters[i]}. {opt}",
                callback_data=f"rva:{mod_id}:{q_idx}:{i}",
            )
        ]
        for i, opt in enumerate(item.options)
    ]
    rows.append([InlineKeyboardButton("🏠 Menu", callback_data="m")])
    return InlineKeyboardMarkup(rows)


def review_next(*, done: bool) -> InlineKeyboardMarkup:
    if done:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🧠 Another review", callback_data="rev")],
                [
                    InlineKeyboardButton("▶️ Continue", callback_data="cont"),
                    InlineKeyboardButton("🏠 Menu", callback_data="m"),
                ],
            ]
        )
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Next ➡️", callback_data="rvn")]]
    )


def module_complete_cta(mod_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🏅 View certificate", callback_data="certs")],
            [
                InlineKeyboardButton("🗺️ Path", callback_data="path"),
                InlineKeyboardButton("▶️ Continue", callback_data="cont"),
            ],
            [InlineKeyboardButton("🏠 Menu", callback_data="m")],
        ]
    )
