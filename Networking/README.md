# Networking

Network clients, scanners, monitors, and availability checks.

Each project lives in its own subdirectory with a `README.md` and a runnable `solution.py`.

- [FTP Program](FTP-Program/) — A file transfer program which can transfer files back and forth from a remote web server.
- [Bandwidth Monitor](Bandwidth-Monitor/) — A small utility program that tracks how much data you have uploaded and downloaded from the net during the course of your current online session and generates a report.
- [Port Scanner](Port-Scanner/) — Enter an IP address and a port range where the program will then attempt to find open ports on the given computer by connecting to each of them. On any successful connections mark the port as open.
- [Mail Checker (POP3 / IMAP)](Mail-Checker/) — The user enters various account information including web server and IP, protocol type (POP3 or IMAP) and the application will check for email at a given interval.
- [Country from IP Lookup](Country-from-IP-Lookup/) — Enter an IP address and find the country that IP is registered in. Optional: Find the IP automatically.
- [Whois Search Tool](Whois-Search-Tool/) — Enter an IP or host address and have it look it up through whois and return the results to you.
- [Site Checker with Time Scheduling](Site-Checker-with-Time-Scheduling/) — An application that attempts to connect to a website or server every so many minutes or at a given time and check if it is up. If it is down, it will notify you by email or by posting a notice on screen.

## Running a project

```bash
cd <Project-Directory>
python3 solution.py --demo
```

Every program supports `--help`; most run interactively with no arguments. Image-based projects list Pillow in `requirements.txt`.
