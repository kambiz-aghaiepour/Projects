# Graphics and Multimedia

Images, animation, audio, and visual rendering.

Each project lives in its own subdirectory with a `README.md` and a runnable `solution.py`.

- [Slide Show](Slide-Show/) — Make an application that shows various pictures in a slide show format. Optional: Try adding various effects like fade in/out, star wipe and window blinds transitions.
- [Stream Video from Online](Stream-Video-from-Online/) — Try to create your own online streaming video player.
- [Mp3 Player](Mp3-Player/) — A simple program for playing your favorite music files. Add features you think are missing from your favorite music player.
- [Watermarking Application](Watermarking-Application/) — Add your own logo or text lightly across the background of pictures so that no one can simply steal your graphics. Optional: Use threading to process multiple images simultaneously.
- [Turtle Graphics](Turtle-Graphics/) — Create a floor of 20 x 20 squares. Using various commands you tell a turtle to draw a line on the floor. You can move forward, left or right, lift or drop pen etc. Optional: read commands from a file.
- [GIF Creator](GIF-Creator/) — A program that puts together multiple images (PNGs, JPGs, TIFFs) to make a smooth GIF that can be exported. Optional: convert small video files to GIFs as well.

## Running a project

```bash
cd <Project-Directory>
python3 solution.py --demo
```

Every program supports `--help`; most run interactively with no arguments. Image-based projects list Pillow in `requirements.txt`.
