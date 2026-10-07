klubliga tennis low feature app minimal design server only mobile first
four pages registration/login, homepage with game score entry, group configuration (admin only), games table
registration:
identification by email, required: last name, first name, sex (m/f). new users receive a magic string auth by email. no other auth.
if they login from another device, email plus magic string (logged into a new device...)
homepage:
your team overview (where you are member) and create team (can be a single player or a double as many as you like, mixed or same-sex)
here we also see wether the tournament has started and in which groups i am in (see next item), or if I was too late, that admin admission is pending.
think about whether there is a better name than teams (which sounds a bit odd for single players) - but keep the terminology straight and simple
groups overview, every team is mapped to one group, decided by admin
list of games to be played by you, including those already completed. that's where I enter my game scores. in the settings (modifiable only by admin) the scoring rules are defined, default is best of three where the third is a match tie break.
group configuration (admin only):
admin can randomly or manually split each tournament (single male, single female, mixed double, mens double, womens double) into two groups (so one or two groups per tournament), depending on number of registrered teams. this grouping needs to be persistent also when teams are added or dropped.
additional late registered teams can be added to a group by admin here as well.
admin can also remove teams. but teams (i.e. either of the players of a double, or a single player) can also withdray themselves from a tournament.
game tables must be updated at every of such changes in the group composition.
settings (admin only):
specify all parameters needed for the app.
admin can start the tournament here. can also resolve incomplete group plays, when the admin knows that no more games will be played there. this is done in the games table, where the admin has these additional options.
admin can thus close the group phase for a group, a tournament or all tournaments. the semi-finals happen only in case of two groups, where first and second of each group play vs. the second and first of the other group, respectively. In case of a single group in a tournament, only finals are done by the first and second.
finals start in the game plan as soon as the required information is available. respective games are then autoamtically added to the game plan of the respective teams and tournaments.
games table:
overview of all groups for a given tournament plus semi-finals and finals where applicable. on top you can choose one of the five tournaements, and below the group standings, a list of all games played in that tournament is displayed, with filter options.

build unit tests for all testable method.
for the framework, use idiomatic minimal django, with no extra packages (unless strictly needed), no javascript framework, just django templates with vanilla javascript and css/html only,
client interactivity can of course use additional vanilla javascript where needed.
when client reactivity is absolutely needed, use the native web components.

the data model consists of users (identified by email, see above), and teams (or another expression you came up with, see above), and then groups (which make up implicitly the tournaments), then games to be played and scored, including those not yet played (undefined score), and those from the semi-finals and finals after the group phase. The definition of each of the five tournaments is implicit through sex and single/double combinations.
teams are created new every season (next season is 2027), the season is displayed in the title line of the app next to the user name and the app title. the groups are selections of teams of same sex or sex-combinations (one of five), so the groups are created new for every season as well. all teams and scores that existed at the end of the tournament are saved in the database for future review.
the season is implicitly the current year - fully automatic, no settings needed for the year.
 
