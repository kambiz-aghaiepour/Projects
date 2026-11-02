# Web

Scraping, local web applications, and internet-powered tools.

Each project lives in its own subdirectory with a `README.md` and a runnable `solution.py`.

- [Page Scraper](Page-Scraper/) — Create an application which connects to a site and pulls out all links, or images, and saves them to a list. Optional: Organize the indexed content, don't allow duplicates, and put the results into an easily searchable index file.
- [Online White Board](Online-White-Board/) — Create an application which allows you to draw pictures, write notes and use various colors to flesh out ideas for projects.
- [Get Atomic Time from Internet Clock](Get-Atomic-Time-from-Internet-Clock/) — This program will get the true atomic time from an atomic time clock on the Internet.
- [Fetch Current Weather](Fetch-Current-Weather/) — Get the current weather for a given zip/postal code. Optional: Try locating the user automatically.
- [Scheduled Auto Login and Action](Scheduled-Auto-Login-and-Action/) — Make an application which logs into a given site on a schedule and invokes a certain action and then logs out.
- [E-Card Generator](E-Card-Generator/) — Make a site that allows people to generate their own little e-cards and send them to other people. Do not use Flash. Use a picture library and perhaps insightful mottos or quotes.
- [Content Management System](Content-Management-System/) — Create a content management system (CMS) like Joomla, Drupal, PHP Nuke etc. Start small. Optional: Allow for the addition of modules/addons.
- [Web Board (Forum)](Web-Board-Forum/) — Create a forum for you and your buddies to post, administer and share thoughts and ideas.
- [CAPTCHA Maker](CAPTCHA-Maker/) — Create an image with letters and numbers for signup forms, then ask the user to enter what they see. It keeps web bots from automatically signing up and spamming.

## Running a project

```bash
cd <Project-Directory>
python3 solution.py --demo
```

Every program supports `--help`; most run interactively with no arguments. Image-based projects list Pillow in `requirements.txt`.
