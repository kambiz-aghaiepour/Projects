# Text

String manipulation, parsing, ciphers, and small text applications.

Each project lives in its own subdirectory with a `README.md` and a runnable `solution.py`.

- [Fizz Buzz](Fizz-Buzz/) — Write a program that prints the numbers from 1 to 100. But for multiples of three print "Fizz" instead of the number and for the multiples of five print "Buzz". For numbers which are multiples of both three and five print "FizzBuzz".
- [Reverse a String](Reverse-a-String/) — Enter a string and the program will reverse it and print it out.
- [Pig Latin](Pig-Latin/) — Pig Latin is a game of alterations played on the English language. To create the Pig Latin form of an English word the initial consonant sound is transposed to the end of the word and an ay is affixed (Ex.: "banana" would yield anana-bay).
- [Count Vowels](Count-Vowels/) — Enter a string and the program counts the number of vowels in the text. For added complexity have it report a sum of each vowel found.
- [Check if Palindrome](Check-if-Palindrome/) — Checks if the string entered by the user is a palindrome. That is that it reads the same forwards as backwards like "racecar".
- [Count Words in a String](Count-Words-in-a-String/) — Counts the number of individual words in a string. For added complexity read these strings in from a text file and generate a summary.
- [Text Editor](Text-Editor/) — Notepad style application that can open, edit, and save text documents. Optional: Add syntax highlighting and other features.
- [RSS Feed Creator](RSS-Feed-Creator/) — Given a link to RSS/Atom Feed, get all posts and display them.
- [Quote Tracker (market symbols etc)](Quote-Tracker/) — A program which can go out and check the current value of stocks for a list of symbols entered by the user. The user can set how often the stocks are checked. For CLI, show whether the stock has moved up or down.
- [Guestbook / Journal](Guestbook-Journal/) — A simple application that allows people to add comments or write journal entries. It can allow comments or not and timestamps for all entries.
- [Vigenere / Vernam / Caesar Ciphers](Vigenere-Vernam-Caesar-Ciphers/) — Functions for encrypting and decrypting data messages. Then send them to a friend.
- [Regex Query Tool](Regex-Query-Tool/) — A tool that allows the user to enter a text string and then in a separate control enter a regex pattern. It will run the regular expression against the source text and return any matches or flag errors in the regular expression.

## Running a project

```bash
cd <Project-Directory>
python3 solution.py --demo
```

Every program supports `--help`; most run interactively with no arguments. Image-based projects list Pillow in `requirements.txt`.
