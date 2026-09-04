"""Inline keyboard builders. Callback data stays well under Telegram's 64-byte limit."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.content_loader import Module, QuizItem
from bot.premium import can_access_module, is_module_free


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
            InlineKeyboardButton("⭐ AvGeek Pro", callback_data="pro"),
            InlineKeyboardButton(daily_label, callback_data="daily:tog"),
        ],
        [
            InlineKeyboardButton("⚖️ Legal", callback_data="legal"),
            InlineKeyboardButton("❓ Help", callback_data="h"),
        ],
    ]
    # streak is shown in the message header, not as a button
    _ = streak
    return InlineKeyboardMarkup(rows)


def welcome_cta() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚀 Start Aerodynamics", callback_data="md:aero"
                )
            ],
            [InlineKeyboardButton("📚 Main menu", callback_data="m")],
        ]
    )


def modules_menu(
    modules: tuple[Module, ...], user_id: int
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for m in modules:
        free = is_module_free(m.id)
        unlocked = can_access_module(user_id, m.id)
        if unlocked:
            prefix = "🆓 " if free else "⭐ "
            label = f"{prefix}{m.emoji} {m.title}"
        else:
            label = f"🔒 {m.emoji} {m.title}"
        rows.append(
            [InlineKeyboardButton(label, callback_data=f"md:{m.id}")]
        )
    rows.append([InlineKeyboardButton("🏠 Main menu", callback_data="m")])
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
                InlineKeyboardButton("📚 All modules", callback_data="mods"),
                InlineKeyboardButton("🏠 Menu", callback_data="m"),
            ],
        ]
    )


def upgrade_cta(module_title: str) -> InlineKeyboardMarkup:
    _ = module_title
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⭐ Unlock with Stars", callback_data="buy")],
            [InlineKeyboardButton("ℹ️ What is Pro?", callback_data="pro")],
            [
                InlineKeyboardButton("📚 Free modules", callback_data="mods"),
                InlineKeyboardButton("🏠 Menu", callback_data="m"),
            ],
        ]
    )


def pro_menu(*, is_premium: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not is_premium:
        rows.append(
            [InlineKeyboardButton("⭐ Buy AvGeek Pro (Stars)", callback_data="buy")]
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
            [InlineKeyboardButton("🏠 Main menu", callback_data="m")],
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


def glossary_prompt() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📚 Modules", callback_data="mods")],
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
