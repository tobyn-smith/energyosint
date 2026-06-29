# Map of the exposure scores, shaded by state.
#
# This uses the usmap package because it draws all 50 states, including Alaska
# and Hawaii, without me having to reposition them by hand. It reads the
# results table that the Python pipeline writes, so run the Python part first.
#
# Packages you need: usmap, ggplot2
#   install.packages(c("usmap", "ggplot2"))
# Then, from the project folder:
#   Rscript analysis/exposure_map.R

suppressPackageStartupMessages({
  library(usmap)
  library(ggplot2)
})

scores <- read.csv("outputs/exposure_index.csv", stringsAsFactors = FALSE)

# usmap matches on a column called "state" (it accepts the two-letter codes),
# which is exactly what the CSV already has.
us_map <- plot_usmap(data = scores, values = "exposure_score",
                     color = "white", linewidth = 0.2) +
  scale_fill_distiller(palette = "OrRd", direction = 1,
                       na.value = "grey85", name = "Exposure\n(0 to 100)") +
  labs(title = "Grid resilience exposure index by state",
       caption = "Public data (EIA 860/861). Higher means more exposed.") +
  theme(legend.position = "right",
        plot.title = element_text(size = 13, face = "bold"),
        plot.caption = element_text(size = 8, color = "grey40"))

ggsave("outputs/exposure_map_r.png", us_map, width = 9, height = 5.5, dpi = 130)
cat("wrote outputs/exposure_map_r.png\n")
