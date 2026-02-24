# The project for CSC_51435

This is an Rust application about the intelligent trash bin.

For now only the simulation part.

Use ' cargo run -- <maze_file> [<point1> <point2> <point3>]' to run the program. The maze file should be a text file with the following format:

```
5 5
#####
#...#
#.#.#
#...#
#####
```
instructions example:
```
cargo run -- maps/default.txt "1,1" "4,3" "5,7"
```
or just
```
cargo run -- maps/default.txt
```
Then it will use the default positions.

Also there should be an executable file in realese, you can run it with
```
./iot-proj-intellibin <maze_file> [<point1> <point2> <point3>]
```
