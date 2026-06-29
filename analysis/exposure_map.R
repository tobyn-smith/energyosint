# Choropleth of the exposure index, drawn with sf + ggplot.
#
# The Python pipeline writes a geopandas map already; this is the version I
# use in writeups because ggplot gives me more control over the look. It reads
# the scored CSV the pipeline produces, joins it onto lower-48 state polygons,
# and also drops a GeoPackage so the result can be opened in QGIS/ArcGIS.
#
# Packages: sf, dplyr, ggplot2, maps
#   install.packages(c("sf", "dplyr", "ggplot2", "maps"))
# Run from the project root:
#   Rscript analysis/exposure_map.R

suppressPackageStartupMessages({
  library(sf)
  library(dplyr)
  library(ggplot2)
  library(maps)
})

scores <- read.csv("outputs/exposure_index.csv", stringsAsFactors = FALSE)

# Scores are keyed on 2-letter codes; the maps polygons use lower-case full
# names. A handful of states come in as multi-part shapes ("michigan:north"),
# so the colon suffix gets stripped before the join.
abbrev <- setNames(tolower(state.name), state.abb)
scores$name <- abbrev[scores$state]

us <- st_as_sf(maps::map("state", plot = FALSE, fill = TRUE))
us$name <- sub(":.*", "", us$ID)
us <- left_join(us, scores, by = "name")

# maps ships the lower 48 only, so AK/HI/DC won't land anywhere. Worth saying
# out loud rather than silently dropping them.
off_map <- setdiff(na.omit(scores$name), unique(us$name))
if (length(off_map)) {
  message("outside the lower-48 polygons: ", paste(off_map, collapse = ", "))
}

p <- ggplot(us) +
  geom_sf(aes(fill = exposure_score), color = "white", linewidth = 0.2) +
  scale_fill_distiller(palette = "OrRd", direction = 1, na.value = "grey85",
                       name = "Exposure\n(0-100)") +
  labs(title = "Grid resilience exposure index by state",
       caption = "Public data (EIA 860/861). Higher = more exposed.") +
  theme_void() +
  theme(plot.title = element_text(size = 13, face = "bold"),
        plot.caption = element_text(size = 8, color = "grey40"),
        legend.position = c(0.92, 0.3))

ggsave("outputs/exposure_map_r.png", p, width = 9, height = 5.5, dpi = 130)

# Spatial export for downstream GIS work — geometry plus the scores attached.
st_write(us, "outputs/exposure_states.gpkg", delete_dsn = TRUE, quiet = TRUE)

cat("wrote outputs/exposure_map_r.png and outputs/exposure_states.gpkg\n")
