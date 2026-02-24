use crate::maze::{Cell, Maze};
use crate::point::TargetPoint;

// @brief renders the maze and all target points to stdout.
// @details
// if a `TargetPoint` occupies a cell, its numeric id is printed instead of the cell symbol.
// `#` is printed for walls and `.` for paths.
// @param maze   reference to the maze
// @param points target points to render
pub fn render(maze: &Maze, points: &[TargetPoint]) {
    print!("\x1B[2J\x1B[H");

    for y in 0..maze.height {
        for x in 0..maze.width {
            if let Some(p) = points.iter().find(|p| p.x == x && p.y == y) {
                print!("{}", p.id);
            } else {
                match maze.grid[y][x] {
                    Cell::Wall => print!("#"),
                    Cell::Path => print!("."),
                }
            }
        }
        println!();
    }
    println!();
}
