# Databases

SQLite-backed applications, analysis, and reporting.

Each project lives in its own subdirectory with a `README.md` and a runnable `solution.py`.

- [SQL Query Analyzer](SQL-Query-Analyzer/) — A utility application which a user can enter a query and have it run against a local database and look for ways to make it more efficient.
- [Remote SQL Tool](Remote-SQL-Tool/) — A utility that can execute queries on remote servers from your local computer across the Internet. It should take in a remote host, user name and password, run the query and return the results.
- [Report Generator](Report-Generator/) — Create a utility that generates a report based on some tables in a database. Generate sales reports based on the order/order details tables or sum up the day's current database activity.
- [Event Scheduler and Calendar](Event-Scheduler-and-Calendar/) — Make an application which allows the user to enter a date and time of an event, event notes and then schedule those events on a calendar. The user can browse or search the calendar. Optional: recurring events.
- [Budget Tracker](Budget-Tracker/) — Write an application that keeps track of a household's budget. The user can add expenses, income, and recurring costs to find out how much they are saving or losing over a period of time.
- [TV Show Tracker](TV-Show-Tracker/) — Make an application which can search various online TV Guide sites, locate the shows/times/channels and add them to a database application. The database can send email reminders that a show is about to start.
- [Travel Planner System](Travel-Planner-System/) — Make a system that allows users to put together their own travel itinerary and keep track of airline / hotel arrangements, points of interest, budget and schedule.

## Running a project

```bash
cd <Project-Directory>
python3 solution.py --demo
```

Every program supports `--help`; most run interactively with no arguments. Image-based projects list Pillow in `requirements.txt`.
