#!/bin/bash
cd /home/sushant/egazette
export PYTHONPATH=/home/sushant/.egazette/lib/python3.14/site-packages/:/home/sushant/:$PYTHONPATH
python3 sync.py -d 60 -s mizoram -s punjabdsa -s cgextraordinary -s cgweekly -s maharashtra -s goa -s keralacompose -s telangana  -s central -s delhi -s chattisgarh -s tamilnadu  -s jharkhand -s madhyapradesh -s uttarakhand -s haryana -s goa -s karnataka_daily -s manipur -s karnataka_weekly -s karnataka_extraordinary -s andhra_extraordinary -s andhra_weekly -s andaman -s arunachal -s assam -s dadranagarhaveli -s gujarat -s jammuandkashmir -s lakshadweep -s meghalaya -s rajasthan_extraordinary -s rajasthan_ordinary -s tripura_ordinary -s tripura_extraordinary -s uttarpradesh_extraordinary -s uttarpradesh_ordinary -s bihar central_extraordinary -s delhi_extraordinary -s odisha_govpress -s odisha_egaz -s himachal -s ladakh -s chandigarh -s sikkim -D /home/sushant/gzdl -f daily-log.txt -D /home/sushant/public/gzdl 1>>dl_out.txt 2>>dl_err.txt 

