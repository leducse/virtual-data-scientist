# Teaching dataset provenance

The CSV files are frozen teaching snapshots, with SHA-256, source/version,
preparation and attribution in catalog.json. This file records provenance and
upstream license declarations; it does not assign a new license to third-party
observations.

- Iris: Fisher (1936), UCI DOI 10.24432/C56C76, CC BY 4.0.
  https://archive.ics.uci.edu/dataset/53/iris
- Wine: Aeberhard and Forina (1991), UCI DOI 10.24432/C5PC7J, CC BY 4.0.
  https://archive.ics.uci.edu/dataset/109/wine
- Breast Cancer Wisconsin (Diagnostic): Wolberg, Street and Mangasarian (1995),
  UCI DOI 10.24432/C5DW2B, CC BY 4.0.
  https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic
- Diabetes progression: Efron, Hastie, Johnstone and Tibshirani, Least Angle
  Regression (2004), via scikit-learn's bundled dataset. The OpenML scikit-learn
  snapshot declares "BSD (from scikit-learn)"; retain this qualified attribution.
  https://www.openml.org/d/41517
- Penguins: Gorman, Williams and Fraser (2014), via the palmerpenguins project by
  Horst, Hill and Gorman. Data are CC0. This teaching view excludes collection
  year, retains mixed types/missing observations, and assumes independent rows.
  https://allisonhorst.github.io/palmerpenguins/
- Compact clusters, curved groups and seasonal sales: project-created synthetic
  observations with recorded seeds; dedicated CC0. Known group labels are never
  clustering/PCA features. Seasonal sales has injected unusual revenue periods.

CC BY 4.0: https://creativecommons.org/licenses/by/4.0/
CC0: https://creativecommons.org/publicdomain/zero/1.0/

OpenML imports are a reviewed subset with fixed dataset IDs, versions, file IDs
and metadata expectations. Their upstream bytes and converted CSV are hashed
at import. Their provider metadata may describe licenses differently from the
original source; both context and provenance are retained in the saved dataset.
