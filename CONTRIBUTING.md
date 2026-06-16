# Как помочь проекту / Contributing

Спасибо, что хочешь помочь! 🙏 Этот проект сделан одним человеком «по приколу», и любая помощь приветствуется — починка бага, новая фича, или просто идея.

*Made by one person for fun. Any help is welcome — bug fixes, features, or just ideas. English below.*

---

## 🇷🇺 По-русски

### Я нашёл баг / у меня идея
Открой **Issue** (вкладка Issues наверху репозитория → New Issue). Опиши:
- Что не так / что хочешь добавить
- Что было на экране (скриншот очень помогает)
- Какой эмулятор и разрешение

Не стесняйся — даже «не работает, вот скрин» уже полезно.

### Я хочу починить код сам
1. **Fork** репозитория (кнопка Fork справа вверху) — получишь свою копию
2. Поправь код у себя
3. **Pull Request** (PR) обратно сюда — я посмотрю и приму

### Как устроен проект (кратко)
```
main.py              — точка входа, цикл захвата экрана
core/
  capture.py         — захват окна/области экрана
  cnn_matcher.py     — распознавание цифр урона нейросетью (CNN)
  tracker.py         — трекинг чисел + расчёт DPS (вся математика тут)
  menu_classifier.py — детект меню для авто-паузы
ui/overlay.py        — оверлей со статистикой
models/              — обученные нейросети (.onnx)
```

### Запуск для разработки
```bash
python -m venv venv
venv\Scripts\activate         # Windows
pip install -r requirements.txt
python main.py
```

### Где скорее всего нужна помощь
См. файл **[KNOWN_ISSUES.md](KNOWN_ISSUES.md)** — там список известных багов и идей. Если что-то оттуда починишь — будет супер.

---

## 🇬🇧 In English

### Found a bug / have an idea?
Open an **Issue** (Issues tab → New Issue). Describe what's wrong, attach a screenshot, mention your emulator and resolution. Even "doesn't work, here's a screenshot" helps.

### Want to fix the code yourself?
1. **Fork** the repo
2. Make your changes
3. Open a **Pull Request** — I'll review and merge

### Project structure
- `main.py` — entry point, screen capture loop
- `core/cnn_matcher.py` — damage digit recognition (CNN)
- `core/tracker.py` — damage tracking + DPS math
- `core/menu_classifier.py` — menu detection for auto-pause
- `ui/overlay.py` — stats overlay
- `models/` — trained neural nets (.onnx)

### Dev setup
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

See **[KNOWN_ISSUES.md](KNOWN_ISSUES.md)** for known bugs and ideas to work on.

---

Нет «глупых» вопросов и «плохих» правок. Просто делай — разберёмся вместе. 🚀
