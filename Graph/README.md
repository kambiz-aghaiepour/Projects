# Graph

Graph construction, traversal, connectivity, and optimization.

Each project lives in its own subdirectory with a `README.md` and a runnable `solution.py`.

- [Graph from Links](Graph-from-Links/) — Create a program that will create a graph or network from a series of links.
- [Eulerian Path](Eulerian-Path/) — Create a program which will take as an input a graph and output either a Eulerian path or a Eulerian cycle, or state that it is not possible. A Eulerian Path starts at one node and traverses every edge of a graph through every node and finishes at another node. A Eulerian cycle is a Eulerian Path that starts and finishes at the same node.
- [Connected Graph](Connected-Graph/) — Create a program which takes a graph as an input and outputs whether every node is connected or not.
- [Dijkstra's Algorithm](Dijkstras-Algorithm/) — Create a program that finds the shortest path through a graph using its edges.
- [Minimum Spanning Tree](Minimum-Spanning-Tree/) — Create a program which takes a connected, undirected graph with weights and outputs the minimum spanning tree of the graph i.e., a subgraph that is a tree, contains all the vertices, and the sum of its weights is the least possible.

## Running a project

```bash
cd <Project-Directory>
python3 solution.py --demo
```

Every program supports `--help`; most run interactively with no arguments. Image-based projects list Pillow in `requirements.txt`.
