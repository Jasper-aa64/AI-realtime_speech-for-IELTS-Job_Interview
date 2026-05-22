# Public Task 1 preview samples

This folder contains two official public Task 1 samples used to preview the chart/image pipeline.

Current items:

- `public_sample_task1_bc_001` - Recycling Materials
- `public_sample_task1_bc_002` - India and China Population

Files:

- `task1_academic.json` - prompt metadata for the two preview samples
- `bc_task1_recycling.png` - local enhanced preview image
- `bc_task1_population.png` - local enhanced preview image

These are not Cambridge IELTS 1-20 prompts. They are only preview materials.

When authorized Cambridge files are ready:

1. Fill `data/ielts/writing/cambridge/example_authorized_materials.json`.
2. Run `scripts/import_cambridge_writing_materials.py`.
3. Check coverage with `--manifest-report`.

The import path validates the Cambridge manifest, copies Task 1 images into `web/static/assets/writing/task1/cambridge/<book>/`, and normalizes the image for display.
