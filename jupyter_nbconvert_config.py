# This config is needed for claude code to run jupyter notebooks in the repo.
# It is read by `python -m nbconvert` when it is run from this directory.
# Together these make a re-run of an unchanged notebook write the same file, byte for byte.
c = get_config()  # noqa: F821

# do not stamp the time of the run into every cell
c.ExecutePreprocessor.record_timing = False
# a cell's prints arrive in chunks whose boundaries change from run to run; join consecutive chunks after the run
c.NotebookExporter.preprocessors = ["nbconvert.preprocessors.CoalesceStreamsPreprocessor"]
