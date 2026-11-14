In the algorithm folder the top file is main_alg.py which uses every other file to create and output all the routes,
which can also be viewed in M_routes.json for debugging.

The only needed function should be main_alg() from "Algorithm/main_alg.py"

NOTE:
***************Everything concerning walking is due to change to rideshare information

Currently main_alg takes:
add1 - a string of the origin address

add2 - a string of the destination address

date - the date for the trip

objective - the objective as in what we want. takes  "cost","arrival","duration"

startime - the starting time for the trip. defaults to "12:01 am"

exclude - what types of transportation we want to exclude.  takes "plane", "train", or "bus". defaults to None

num_paths - how many routes do you want. defaults to 3



Example use:
today = date.today()
tomorrow = today + timedelta(days=1)

add1 = "1301 Pennsylvania St Denver, CO 80203"
add2 = "1000 E Georgia Ave Ruston, LA 71272"
objective = "duration"
starttime = "8:00 am"
//not gonna exclude anything
//leave it to 3 paths

results = main_alg(add1, add2, tommorow, objective=objective, start_time=starttime, exclude=None, num_paths=3)



resulting Format from main_alg (see also "Algorithm/M_routes.json"):
where query was the search params
and routes are given a rank where the least rank is the cheapest cost
and each route has information on each of the legs in the journey
Some info will not be neccessary to display or use

{
  "query": {
    "origin_address": "",
    "destination_address": "",
    "origin": {
      "LAT": null,
      "LONG": null
    },
    "destination": {
      "LAT": null,
      "LONG": null
    },
    "date": "",
    "start_time": "",
    "objective": "",
    "excluded": null,
    "num_paths_requested": null
  },
  "num_routes": null,
  "routes": [
    {
      "rank": null,
      "total_cost": null,
      "currency": "",
      "total_time_min": null,
      "departure": "",
      "arrival": "",
      "num_legs": null,
      "modes": [
        ""
      ],
      "legs": [
        {
          "leg_number": null,
          "type": "",
          "name": "",
          "scope": "",
          "cost": null,
          "departure": "",
          "arrival": "",
          "duration_min": null,
          "wait_before_min": null,
          "from": {
            "City": "",
            "State": "",
            "Name": "",
            "Station ID": "",
            "GPS": {
              "LAT": null,
              "LONG": null
            }
          },
          "to": {
            "City": "",
            "State": "",
            "Name": "",
            "Station ID": "",
            "GPS": {
              "LAT": null,
              "LONG": null
            }
          },
          "source_record": {
            "method": {
              "info": {
                "Type": "",
                "Name": "",
                "Scope": "",
                "Cost": null,
                "Currency": "",
                "Price Basis": "",
                "Travel Time (min)": null,
                "Distance (meters)": null,
                "Transfers": null,
                "Trip ID": ""
              },
              "starting_location": {
                "City": "",
                "State": "",
                "Name": "",
                "Station ID": "",
                "GPS": {
                  "LAT": null,
                  "LONG": null
                }
              },
              "destination": {
                "City": "",
                "State": "",
                "Name": "",
                "Station ID": "",
                "GPS": {
                  "LAT": null,
                  "LONG": null
                }
              }
            }
          }
        }
      ]
    }
  ]
}
