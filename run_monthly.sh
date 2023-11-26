echo 'Activate venv'
. /home/cruz/development/venvs/ff3_importer/bin/activate

echo 'Run monthly.py'
python3 /home/cruz/development/ff3_importer/run_jobs.py monthly

if [ $? -eq 0 ]; then
    echo 'Run successful!'
    exit 0
else
    echo 'Run failed!'
    exit 1
fi

