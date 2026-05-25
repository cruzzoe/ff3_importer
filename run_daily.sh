echo 'Activate venv'
. /home/cruz/development/venvs/ff3_importer/bin/activate

echo 'Run monthly.py'
xvfb-run --server-args="-screen 0 1920x1080x24" /home/cruz/development/venvs/ff3_importer/bin/python /home/cruz/development/ff3_importer/run_jobs.py --mode daily
#python3 /home/cruz/development/ff3_importer/run_jobs.py --mode daily 

if [ $? -eq 0 ]; then
    echo 'Run successful!'
    exit 0
else
    echo 'Run failed!'
    exit 1
fi
