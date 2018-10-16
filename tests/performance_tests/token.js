const payload = {
  service: "admin",
  username: "internal"
};
var jwt = new Buffer("jwt schema").toString("base64") + "." + new Buffer(JSON.stringify(payload)).toString("base64") + "." + new Buffer("dummy signature").toString("base64");
console.log(jwt);
