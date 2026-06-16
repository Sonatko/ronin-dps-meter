# Известные баги и идеи / Known Issues & Ideas

Честный список того, что ещё не идеально. Если хочешь помочь — выбирай отсюда!
*Honest list of what's not perfect yet. Pick something to help with!*

Метки: 🟢 хорошая первая задача (легко) · 🟡 средне · 🔴 сложно

---

## 🐛 Известные баги / Known bugs

- 🟡 **Дальний бой не считается.** Урон по дальним врагам и на краю экрана не распознаётся (цифры мелкие/за кадром). Можно улучшить распознавание мелких чисел или мульти-зонный захват.
  *Ranged/off-screen damage isn't counted — digits too small or off-frame.*

- 🟡 **Светлое меню инвентаря иногда не ловится авто-паузой.** Классификатор меню обучен в основном на тёмных меню. Нужно дообучить на светлых экранах.
  *Light inventory menus sometimes aren't caught by auto-pause.*

- 🟡 **Наложение цифр при быстрых комбо.** Когда несколько чисел урона всплывают друг на друге, часть может слипнуться или потеряться.
  *Overlapping damage numbers during fast combos can merge/be missed.*

- 🟢 **Окно эмулятора нужно крупное.** На маленьком окне цифры мелкие → хуже распознавание. Можно добавить апскейл ROI перед подачей в CNN.
  *Small emulator window = small digits = worse recognition. Could upscale ROI before CNN.*

---

## 💡 Идеи для фич / Feature ideas

- 🟢 **Сохранять лог боя** в файл (CSV/JSON) — чтобы анализировать урон после боя.
  *Save combat log to a file for post-battle analysis.*

- 🟢 **Горячая клавиша для сброса/паузы** — сейчас только кнопка мышью.
  *Hotkey for reset/pause instead of only the mouse button.*

- 🟡 **Графики** — DPS во времени, как в WoW Details.
  *Damage-over-time graph like WoW Details.*

- 🟡 **Поддержка других похожих игр** — архитектура общая, можно дообучить CNN под другую игру.
  *Support for other similar games — retrain the CNN.*

- 🔴 **Версия под Linux/Mac** — сейчас только Windows (захват экрана через dxcam/Windows API).
  *Linux/Mac port — currently Windows-only.*

- 🟡 **Авто-определение области игры** — чтобы не обводить мышью вручную.
  *Auto-detect the game window/area instead of manual selection.*

---

## ⚙️ Как улучшить распознавание (для тех, кто в ML)

Модели в `models/` обучены на ограниченном датасете (один эмулятор, одно разрешение, русская локализация). Помощь нужна с:
- 🔴 Расширением датасета (разные эмуляторы/разрешения/языки игры)
- 🟡 Дообучением CNN на ложных срабатываниях

Скрипты обучения не в релизе (тяжёлые), но если возьмёшься — напиши в Issues, скину.

*ML models trained on a limited dataset. Help wanted: more diverse training data, retraining on false positives. Training scripts available on request (open an Issue).*

---

Не знаешь с чего начать? Бери задачу с меткой 🟢 — они самые простые.
*New here? Pick a 🟢 task — those are the easiest.*
