# Your work

One folder per job: `jobs/NN-short-name/` with `geometry.py` or `part.step`, `job.json`
and the outputs (`results.json`, `report.html`, `report.pdf`).

    ./ea fea new jobs/01-my-part -a static
    ./ea fea run jobs/01-my-part --converge --report

Large regenerable files (`job.inp`, `job.frd`, `view.json`, `viewer.html`, `plots/`) are
not committed; `./ea fea run <job> --report` recreates them.
