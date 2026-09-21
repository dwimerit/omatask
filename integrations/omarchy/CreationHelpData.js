.pragma library
var sections = [
  {
    "title": "Create a task",
    "body": "Enter a title and optional settings in the input above, then press Enter. Titles can use any language; keywords are in English. Settings may appear in any order. Insert example fills the input for editing and does not create a task.\nPress / in an empty new-task input to search instead. A slash inside a title stays ordinary text.",
    "examples": [
      "Buy milk tomorrow 18:00"
    ]
  },
  {
    "title": "Daily goals: several reminders each day",
    "body": "daily 8x 08:00-22:00 schedules eight reminders evenly between 08:00 and 22:00, including both endpoints. Times are rounded to the nearest minute.\n8x is the number of reminders per day; count 30 limits the series to 30 days. The longer spelling is daily goal 8 between 08:00-22:00.\nWithout a date, the task starts today, or tomorrow if the window has ended. Earlier times on the creation day are skipped. Add tomorrow to start with a full day.\nComplete the task once, after meeting your daily goal, to schedule the next day. The daily deadline is the end of the window.\nUse a same-day window with at least one minute per interval. With 1x, the reminder is at the end. Do not combine a window with remind or an hourly/weekly recurrence.",
    "examples": [
      "Drink water daily 8x 08:00-22:00",
      "Take a screen break tomorrow daily 4x 09:00-18:00"
    ]
  },
  {
    "title": "Dates and times",
    "body": "today / tomorrow — today or tomorrow.\nmonday, tuesday, wednesday, thursday, friday, saturday, sunday — the next matching weekday, including today.\nAdd HH:MM: tomorrow 18:30. Without a time, these day keywords mean 09:00.\nExact date: YYYY-MM-DD or YYYY-MM-DD HH:MM. A date alone means midnight. ISO timestamps work too: YYYY-MM-DDTHH:MM:SS+03:00.\nHH:MM alone means the next occurrence of that time, today or tomorrow. An explicit today with a past time remains today and is due immediately.",
    "examples": [
      "Call Alex tomorrow 14:30",
      "Check email 18:00"
    ]
  },
  {
    "title": "Relative deadlines",
    "body": "in 10m — in ten minutes; in 2h — in two hours; in 3d — in three days; in 1w — in one week.\nm = minutes, h = hours, d = days, w = weeks. Use a positive whole number. A task has one deadline: do not combine two dates or a date with in.",
    "examples": [
      "Take a break in 25m"
    ]
  },
  {
    "title": "Repeating tasks",
    "body": "daily / weekly / monthly — every day / week / month.\nevery 2m / every 2h / every 2d / every 2w / every 2mo — every N minutes / hours / days / weeks / months.\nevery mon,wed,fri — selected weekdays. Available abbreviations: mon,tue,wed,thu,fri,sat,sun.\nA repeating task needs a first deadline. With selected weekdays, that deadline must match one of them. Daily windows set their own deadline.\nCompleting the current occurrence schedules the next one.",
    "examples": [
      "Exercise tomorrow 09:00 daily",
      "Go to the gym monday 09:00 every mon,wed,fri"
    ]
  },
  {
    "title": "Repeat limits",
    "body": "count 30 — thirty occurrences in total, including the first.\nuntil YYYY-MM-DDT23:59 — include deadlines up to that instant. You can also use until \"tomorrow 23:59\".\ncount and until require daily / weekly / monthly / every. Without a limit, the series continues indefinitely. until limits scheduled deadlines, not the actual time you complete them.",
    "examples": [
      "Practice English tomorrow 19:00 daily count 30"
    ]
  },
  {
    "title": "Reminders and sound",
    "body": "A task with a deadline automatically gets a reminder at that time. The worker may take up to ten seconds to deliver it.\nremind 30m / remind 1h / remind 1d / remind 1w — remind before the deadline. Explicit reminders replace the automatic deadline reminder.\nremind at 18:00 — the next 18:00.\nremind at \"tomorrow 18:00\" — a specific instant, even without a task deadline. ISO timestamps are also supported.\nRepeat remind to set several reminders. Use remind at for tasks without a deadline. Do Not Disturb suppresses the popup and sound.",
    "examples": [
      "Team meeting tomorrow 15:00 remind 30m remind 1h",
      "Call Alex remind at \"tomorrow 10:00\""
    ]
  },
  {
    "title": "Priority, tags and projects",
    "body": "!low / !normal / !high / !urgent — priority; normal is the default.\n#work #home — one or more tags, without spaces.\n+Work — a project; +\"Side Project\" — a project name with spaces. A task has one project. Combine these settings with deadlines, repeats and daily windows.",
    "examples": [
      "Prepare report tomorrow 16:00 !high #work +\"Side Project\""
    ]
  },
  {
    "title": "Titles and quotation marks",
    "body": "Words that are not settings become the task title. Quotes group a value containing spaces: +\"Side Project\", remind at \"tomorrow 18:00\". Close every quotation mark.\nKeywords such as today, daily, remind, goal, between and count are reserved, as are daily-window tokens such as 8x. To keep them as ordinary title text, use omatask add --literal in a terminal. Description and other CLI options are listed below."
  },
  {
    "title": "Terminal: basic creation options",
    "body": "These flags are for the terminal, not the widget input.\nomatask add \"Title and settings\"\n--literal — keep the title as written without parsing keywords.\n--description \"Text\" — description.\n--due \"tomorrow 18:00\" — deadline; --due none — no deadline.\n--priority low|normal|high|urgent — priority.\n--tag work — tag; repeat this flag for multiple tags.\n--project \"Side Project\" — project.\nFlags in this section override the corresponding settings in the input string. A daily window needs daily recurrence and a deadline at or after its last reminder.\nUse omatask add --help to print the command reference."
  },
  {
    "title": "Terminal: repeats and reminders",
    "body": "--repeat minute|hour|day|week|month — frequency; --repeat none — no repeat.\n--interval N — every N periods.\n--count N — N occurrences in total.\n--until \"YYYY-MM-DD 23:59\" — end of the series.\n--weekdays mon,wed,fri — weekdays for --repeat week.\n--interval, --count, --until and --weekdays require --repeat.\n--remind 30m — remind before the deadline; repeatable.\n--remind-at \"tomorrow 18:00\" — an absolute reminder; repeatable.\nReminder flags add to reminders in the input string.\nGlobal flags go before add: --timezone Europe/London, --db /path/tasks.db, --json.\nExample: omatask --timezone Europe/London add \"Report\" --literal --due \"tomorrow 18:00\" --description \"For the team\" --priority high --tag work --remind 30m"
  }
];
