# SkyLink

**Язык / Language:** раскройте нужный блок ниже · expand a section below

<details open>
<summary><strong>Русский</strong></summary>

**Версия 2.0.4** · **Vistory**  
Агент эскадрильи для Elite Dangerous и портала [SkyBioML](https://skybioml.space)

---

SkyLink — небольшой агент для Windows. Он читает журнал игры и передаёт данные на портал **вашей эскадрильи**: положение, события, статус связи. На сайте работают синхронизация командира, Road 2 Riches и другие инструменты HQ.

Программа живёт в трее: свернули окно — играете как обычно, штаб эскадрильи остаётся в курсе.

### Мессенджер (Messages)

Кнопка **Messages** в окне и в трее открывает **отдельное окно** с чатом портала (каналы, личные сообщения, синхронизация с сайтом и Discord).

- **Запущенный Elite Dangerous для чата не нужен** — достаточно сохранённого API-ключа в SkyLink.
- На портале для вашего ранга должно быть право доступа.
- Статус **WAITING FOR SIGNAL** относится только к телеметрии из журнала, не к Messages.

---

## Скачать

**[SkyLink.exe (релиз 2.0.4)](https://github.com/Vist0ry/SkyLink/releases/download/2.0.4/SkyLink.exe)** · [все релизы](https://github.com/Vist0ry/SkyLink/releases)

---

## Как начать

1. Войдите на [skybioml.space](https://skybioml.space) через Discord.
2. В **HQ → SKYLINK API** создайте ключ и скопируйте его.
3. Запустите **SkyLink**, **+ ADD ACCOUNT** → вставьте ключ → **SAVE**.
4. (Телеметрия) Запустите Elite Dangerous — имя командира в игре должно совпадать с профилем на портале.
5. (Чат) **Messages** — откроется окно чата, если ключ и права на сайте в порядке.

---

## Нужно для работы

| | Телеметрия (журнал) | Messages (чат) |
|--|---------------------|----------------|
| Windows 10/11 | да | да |
| Elite Dangerous | да | нет |
| Аккаунт на [skybioml.space](https://skybioml.space) | да | да |
| API-ключ SkyLink | да | да |
| Право доступа к мессенджеру на портале | нет | да |

Ключ API хранится только на вашем компьютере (`%APPDATA%\SkyLink`).

---

## Если Messages не открывается

1. Обновитесь до **2.0.4** (не старее).
2. Проверьте ключ: **CHANGE API** → сохранить снова.
3. Убедитесь, что у вашего ранга на портале есть право доступа к мессенджеру.
4. Лог: `%APPDATA%\SkyLink\skylink_client.log` — строки `Messages token OK` или `Messages error`.

---

*SkyLink · агент эскадрильи · Vistory · 2026*

</details>

<details>
<summary><strong>English</strong></summary>

**Version 2.0.4** · **Vistory**  
Squadron agent for Elite Dangerous and the [SkyBioML](https://skybioml.space) portal

---

SkyLink is a small Windows agent. It reads your game journal and sends data to **your squadron** portal: position, events, link status. That powers commander sync, Road 2 Riches, and other HQ tools on the site.

It runs in the system tray: minimize the window, play as usual — your wing HQ stays updated.

### Messenger (Messages)

The **Messages** button in the window and tray opens a **dedicated window** with the portal chat (channels, DMs, synced with the website and Discord).

- **Elite Dangerous does not need to be running for chat** — a saved API key in SkyLink is enough.
- Your rank on the portal must have access permission.
- **WAITING FOR SIGNAL** only affects journal telemetry, not Messages.

---

## Download

**[SkyLink.exe (release 2.0.4)](https://github.com/Vist0ry/SkyLink/releases/download/2.0.4/SkyLink.exe)** · [all releases](https://github.com/Vist0ry/SkyLink/releases)

---

## Getting started

1. Sign in at [skybioml.space](https://skybioml.space) with Discord.
2. In **HQ → SKYLINK API**, create a key and copy it.
3. Run **SkyLink**, **+ ADD ACCOUNT** → paste the key → **SAVE**.
4. (Telemetry) Launch Elite Dangerous — your in-game commander name must match your portal profile.
5. (Chat) **Messages** — opens the chat window when the key and site permissions are valid.

---

## Requirements

| | Telemetry (journal) | Messages (chat) |
|--|----------------------|-----------------|
| Windows 10/11 | yes | yes |
| Elite Dangerous | yes | no |
| Account at [skybioml.space](https://skybioml.space) | yes | yes |
| SkyLink API key | yes | yes |
| Messenger access on the portal | no | yes |

Your API key is stored only on your PC (`%APPDATA%\SkyLink`).

---

## If Messages does not open

1. Update to **2.0.4** (not older).
2. Re-save your key: **CHANGE API**.
3. Make sure your rank on the portal has messenger access.
4. Log: `%APPDATA%\SkyLink\skylink_client.log` — look for `Messages token OK` or `Messages error`.

---

*SkyLink · squadron agent · Vistory · 2026*

</details>
