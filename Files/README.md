# Files

File formats, converters, generators, and local utilities.

Each project lives in its own subdirectory with a `README.md` and a runnable `solution.py`.

- [Quiz Maker](Quiz-Maker/) — Make an application which takes various questions from a file, picked randomly, and puts together a quiz for students. Each quiz can be different and then reads a key to grade the quizzes.
- [Sort Excel/CSV File Utility](Sort-Excel-CSV-File-Utility/) — Reads a file of records, sorts them, and then writes them back to the file. Allow the user to choose various sort styles and sorting based on a particular field.
- [Create Zip File Maker](Create-Zip-File-Maker/) — The user enters various files from different directories and the program zips them up into a zip file. Optional: Apply actual compression to the files.
- [PDF Generator](PDF-Generator/) — An application which can read in a text file, HTML file or some other file and generates a PDF file out of it.
- [Mp3 Tagger](Mp3-Tagger/) — Modify and add ID3v1 tags to MP3 files. See if you can also add the album art into the MP3 file's header as well as other ID3v2 tags.
- [Code Snippet Manager](Code-Snippet-Manager/) — A utility program that allows coders to store functions, classes or other tidbits to save for later, organized by the type of snippet or language.

## Running a project

```bash
cd <Project-Directory>
python3 solution.py --demo
```

Every program supports `--help`; most run interactively with no arguments. Image-based projects list Pillow in `requirements.txt`.
