use std::fs;
use std::path::Path;

/// @brief the type of a single cell
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Cell {
    Wall,
    Path,
}

/// @brief stores the maze grid and dimensions
/// @details origin at the top-left corner
#[derive(Debug)]
pub struct Maze {
    pub grid: Vec<Vec<Cell>>,
    pub width: usize,
    pub height: usize,
}

impl Maze {
    /// @brief loads a maze from a plain-text file
    /// @details
    /// `#` characters are parsed as `Cell::Wall`
    /// All other characters are parsed as `Cell::Path`
    /// all empty lines are skipped. For now, every row must have the same number of columns (if not, error)
    /// @param path the path to the map file
    /// @return
    /// `Ok(Maze)` on success.
    /// `Err(String)` if the file is abnormal like empty or other errors
    pub fn load_from_file(path: &Path) -> Result<Self, String> {
        let content = fs::read_to_string(path)
            .map_err(|e| format!("Failed to read map file: {}", e))?;

        let grid: Vec<Vec<Cell>> = content
            .lines()
            .filter(|line| !line.is_empty())
            .map(|line| {
                line.chars()
                    .map(|ch| match ch {
                        '#' => Cell::Wall,
                        _ => Cell::Path,
                    })
                    .collect()
            })
            .collect();

        if grid.is_empty() {
            return Err("Map file is empty".to_string());
        }

        let height = grid.len();
        let width = grid[0].len();

        for (i, row) in grid.iter().enumerate() {
            if row.len() != width {
                return Err(format!(
                    "Row {} has {} columns, expected {}",
                    i,
                    row.len(),
                    width
                ));
            }
        }

        Ok(Maze { grid, width, height })
    }

    /// @brief checks whether walkable.
    /// @param x Column index (0-based, increases to the right).
    /// @param y Row index (0-based, increases downward).
    /// @return `true` if the cell is within bounds and is a `Cell::Path`; `false` otherwise.
    pub fn is_walkable(&self, x: usize, y: usize) -> bool {
        if x >= self.width || y >= self.height {
            return false;
        }
        self.grid[y][x] == Cell::Path
    }
}
