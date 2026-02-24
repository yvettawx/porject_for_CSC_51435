use crate::maze::Maze;

// @brief cardinal directions 
#[derive(Debug, Clone, Copy)]
pub enum Direction {
    North,
    South,
    East,
    West,
}

impl Direction {
    // @brief parse directions from a single-character string
    // @details accept: `"N"`, `"S"`, `"E"`, `"W"`
    // @param s input string
    // @return `Ok(Direction)` on success, or `Err(String)` if the string is abnormal
    pub fn from_str(s: &str) -> Result<Self, String> {
        match s.to_uppercase().as_str() {
            "N" => Ok(Direction::North),
            "S" => Ok(Direction::South),
            "E" => Ok(Direction::East),
            "W" => Ok(Direction::West),
            _ => Err(format!("Unknown direction: '{}'. Use N/S/E/W.", s)),
        }
    }

    // @brief returns the (dx, dy) unit vector for this direction
    // @return move instruction
    fn delta(&self) -> (isize, isize) {
        match self {
            Direction::North => (0, -1),
            Direction::South => (0, 1),
            Direction::East => (1, 0),
            Direction::West => (-1, 0),
        }
    }
}

// @brief named points
// @details each point has a unique identifier and a current (x, y) position.
#[derive(Debug)]
pub struct TargetPoint {
    pub id: u8,
    pub x: usize,
    pub y: usize,
}

impl TargetPoint {
    // @brief creates a new `TargetPoint`
    // @param id   unique identifier
    // @param x    column index
    // @param y    row index
    // @return the new `TargetPoint`
    pub fn new(id: u8, x: usize, y: usize) -> Self {
        TargetPoint { id, x, y }
    }

    // @brief move as instructions
    // @details
    // move the `Targetpoint` as instructions and stop it in certain conditions
    // @param dir  direction
    // @param dist maximum distance
    // @param maze reference ro the maze
    // @return number of actual steps moved
    pub fn move_by(&mut self, dir: Direction, dist: usize, maze: &Maze) -> usize {
        let (dx, dy) = dir.delta();
        let mut moved = 0;

        for _ in 0..dist {
            let nx = self.x as isize + dx;
            let ny = self.y as isize + dy;

            if nx < 0 || ny < 0 {
                break;
            }

            let nx = nx as usize;
            let ny = ny as usize;

            if !maze.is_walkable(nx, ny) {
                break;
            }

            self.x = nx;
            self.y = ny;
            moved += 1;
        }

        moved
    }
}

// @brief user commands
#[derive(Debug)]
pub struct Command {
    pub point_id: u8,
    pub direction: Direction,
    pub distance: usize,
}

impl Command {
    // @brief parse commands
    // @details
    // expected format: `"<ID> <DIR> <DIST>"`
    // `ID`   - identifier
    // `DIR`  - direction
    // `DIST` - distance
    // @param input raw command
    // @return `Ok(Command)` on success, or `Err(String)` describing the parse failure.
    pub fn parse(input: &str) -> Result<Self, String> {
        let parts: Vec<&str> = input.trim().split_whitespace().collect();
        if parts.len() != 3 {
            return Err("Command format: ID DIR DIST (e.g. '1 N 2')".to_string());
        }

        let point_id: u8 = parts[0]
            .parse()
            .map_err(|_| format!("Invalid point ID: '{}'", parts[0]))?;

        let direction = Direction::from_str(parts[1])?;

        let distance: usize = parts[2]
            .parse()
            .map_err(|_| format!("Invalid distance: '{}'", parts[2]))?;

        if distance == 0 {
            return Err("Distance must be > 0".to_string());
        }

        Ok(Command {
            point_id,
            direction,
            distance,
        })
    }
}
