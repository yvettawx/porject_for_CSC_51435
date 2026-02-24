mod maze;
mod point;
mod renderer;

use std::env;
use std::io::{self, Write};
use std::path::Path;

use maze::Maze;
use point::{Command, TargetPoint};

// @brief application entry point.
// @details
// loads maze from the path given as the first command-line argument
// place up to three target points (can be instructed)
// or falling back to hardcoded defaults
// accept movement commands of the form `"<ID> <DIR> <DIST>"`.
// `q` or `quit` to exit.
fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: {} <map_file> [x1,y1 x2,y2 x3,y3]", args[0]);
        eprintln!("Example: {} maps/default.txt 1,1 4,3 5,7", args[0]);
        std::process::exit(1);
    }

    let map_path = Path::new(&args[1]);
    let maze = match Maze::load_from_file(map_path) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("Error loading map: {}", e);
            std::process::exit(1);
        }
    };

    let mut points = Vec::new();
    for i in 0..3u8 {
        let (x, y) = if args.len() > (2 + i as usize) {
            parse_position(&args[2 + i as usize]).unwrap_or_else(|e| {
                eprintln!("Invalid position for point {}: {}", i + 1, e);
                std::process::exit(1);
            })
        } else {
            default_positions(i)
        };

        if !maze.is_walkable(x, y) {
            eprintln!("Point {} at ({},{}) is not on a walkable cell!", i + 1, x, y);
            std::process::exit(1);
        }

        points.push(TargetPoint::new(i + 1, x, y));
    }

    renderer::render(&maze, &points);

    loop {
        print!("> ");
        io::stdout().flush().unwrap();

        let mut input = String::new();
        if io::stdin().read_line(&mut input).unwrap() == 0 {
            break; // EOF
        }

        let input = input.trim();
        if input.eq_ignore_ascii_case("quit") || input.eq_ignore_ascii_case("q") {
            break;
        }

        if input.is_empty() {
            continue;
        }

        let cmd = match Command::parse(input) {
            Ok(c) => c,
            Err(e) => {
                println!("Error: {}", e);
                continue;
            }
        };

        match points.iter_mut().find(|p| p.id == cmd.point_id) {
            Some(p) => {
                let moved = p.move_by(cmd.direction, cmd.distance, &maze);
                if moved < cmd.distance {
                    println!(
                        "Point {} moved {} steps (blocked by wall after {} steps)",
                        cmd.point_id, moved, moved
                    );
                }
            }
            None => {
                println!(
                    "No point with ID {}. Available: {}",
                    cmd.point_id,
                    points.iter().map(|p| p.id.to_string()).collect::<Vec<_>>().join(", ")
                );
                continue;
            }
        }

        renderer::render(&maze, &points);
    }
}

// @brief parse position strings to coordinates
// @param s input string
// @return `Ok((x, y))` on success, or `Err(String)` if the format is invalid.
fn parse_position(s: &str) -> Result<(usize, usize), String> {
    let parts: Vec<&str> = s.split(',').collect();
    if parts.len() != 2 {
        return Err("Format: x,y".to_string());
    }
    let x: usize = parts[0].parse().map_err(|_| "Invalid x")?;
    let y: usize = parts[1].parse().map_err(|_| "Invalid y")?;
    Ok((x, y))
}

// @brief returns a hardcoded default position for a given point index.
// @param index zero-based index of the target point.
// @return `(x, y)` tuple representing the default position.
fn default_positions(index: u8) -> (usize, usize) {
    match index {
        0 => (1, 1),
        1 => (4, 3),
        2 => (5, 7),
        _ => (1, 1),
    }
}
