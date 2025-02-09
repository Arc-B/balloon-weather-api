Windborne's live constellation API:<br/>
**https://a.windbornesystems.com/treasure/00.json** <br/>
The above link gives current positions of their balloons. 01.json is the location one hour ago, 03.json three hours ago, and so on till 23h ago.

OpenWeather API:<br/>
https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={API_KEY} <br/>
This provides real-time weather updates like temperature, pressure, wind speed, and weather description. 

I have combined the above two APIs to get the real-time weather conditions based on the balloon coordinates. 

My API is hosted on the following site.<br/>
https://balloon-weather-api.onrender.com/balloon_weather

Replace /balloon_weather with /dashboard to see the live interactive dashboard.
