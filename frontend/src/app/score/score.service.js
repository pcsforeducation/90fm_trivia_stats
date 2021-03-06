'use strict';

angular.module('triviastats')
  .service('Score', ['djResource', '$q', '$http', 'BACKEND_SERVER', function (djResource, $q, $http, BACKEND_SERVER) {
    var service = {};
    console.log(BACKEND_SERVER + 'scores\/');
    var api = djResource(BACKEND_SERVER + 'scores\/');
    var teamsApi = djResource(BACKEND_SERVER + 'teams\/');
    //$http.get(BACKEND_SERVER + 'scores\/')

    service.teamScores = function (team, year) {
      return api.query({
        'team_name': team,
        'ordering': '-year,team_name,-hour',
        'year': year
      });
    };

    service.hourScores = function (hour, year, results) {
      var args = {
        'ordering': '-score'
      };
      if (hour !== undefined) {
        args['hour'] = hour;
        //args['ordering'] = '';
      }
      else {
        args['ordering'] = '-year,-hour,-score'
      }
      if (year !== undefined) {
        args['year'] = year;
      }
      if (results !== undefined) {
        args['results'] = results
      }
      return api.query(args);
    };

    service.yearScores = function (year, success_callback, results) {
      var args = {
        'ordering': 'team_name,hour',
        'year': year
      };

      if (results !== undefined) {
        args['results'] = results
      }

      console.log(success_callback);
      return api.query(args, success_callback, success_callback);
    };

    service.search = function (searchString) {
      return api.query({
        // User team name to keep them grouped properly
        'ordering': '-year,team_name,-hour',
        'search': searchString
      });
    };

    service.teamList = function () {
      return teamsApi.query({});
    };

    return service;
  }]);
