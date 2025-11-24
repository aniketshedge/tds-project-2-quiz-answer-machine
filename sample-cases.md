# Sample or Demo cases

The following are two demo cases. Check if these will be handled by the code:

##  Question 1: https://tds-llm-analysis.s-anand.net/demo
####  HTML page source:
```
  POST this JSON to <span class="origin"></span>/submit

  <pre>
  {
    "email": "your email",
    "secret": "your secret",
    "url": "<span class="origin"></span>/demo",
    "answer": "anything you want"
  }
  </pre>

  <script type="module">
  for (const el of document.querySelectorAll(".origin")) {
    el.innerHTML = window.location.origin;
  }
  </script>
```
###  Response if correct:
```
  {
      "correct": true,
      "reason": "",
      "url": "https://tds-llm-analysis.s-anand.net/demo-scrape?email=21f1006362%40ds.study.iitm.ac.in&id=7351",
      "delay": null
  }
```


##  Question 2: https://tds-llm-analysis.s-anand.net/demo-scrape?email=21f1006362%40ds.study.iitm.ac.in&id=7351
####  Source:
```
  <div id="question"></div>

  <script>
  const urlParams = new URLSearchParams(location.search.replace(/^\?/, ""));
  const email = urlParams.get("email");
  const code = `U2NyYXBlIDxhIGhyZWY9Ii9kZW1vLXNjcmFwZS1kYXRhP2VtYWlsPSRFTUFJTCI+L2RlbW8tc2NyYXBlLWRhdGE/
  ZW1haWw9JEVNQUlMPC9hPiAocmVsYXRpdmUgdG8gdGhpcyBwYWdlKS4KR2V0IHRoZSBzZWNyZXQgY29kZSBmcm9tIHRoaXMgcGFnZS4KUE9TVCB0aGUgc2VjcmV0IGNvZGUgYmFjayB0byA8YSBocmVmPSIvc3VibWl0Ij4vc
  3VibWl0PC9hPgoKPHByZT4KewogICJlbWFpbCI6ICIkRU1BSUwiLAogICJzZWNyZXQiOiAieW91ciBzZWNyZXQiLAogICJ1cmwiOiAidGhpcyBwYWdlJ3MgVVJMIiwKICAiYW5zd2VyIjogInRoZSBzZWNyZXQgY29kZSB5b3
  Ugc2NyYXBlZCIKfQo8L3ByZT4=`;
  const content = email
    ? atob(code).replace(/\$EMAIL/g, email)
    : "Please provide ?email=";
  document.querySelector("#question").innerHTML = content;
  </script>
```

####  Source of https://tds-llm-analysis.s-anand.net/demo-scrape-data?email=21f1006362@ds.study.iitm.ac.in:
```
  <div id="question"></div>
  <script src="demo-scrape.js" type="module"></script>
```

####  Source of https://tds-llm-analysis.s-anand.net/demo-scrape.js:
```
  import { emailNumber } from "./utils.js";

  const code = await emailNumber();
  document.querySelector("#question").innerHTML = code
    ? `Secret code is <strong>${code}</strong> and not <em>${code + Math.round(Math.random() * 1000)}</em>.`
    : "Please provide ?email=";
```

###  Response if correct:
```
  {
      "correct": true,
      "reason": "",
      "url": "https://tds-llm-analysis.s-anand.net/demo-audio?email=21f1006362%40ds.study.iitm.ac.in&id=7358",
      "delay": 173
  }
```
