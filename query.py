query {
  MediaListCollection(userName: "robert054321", type: ANIME, sort:[SCORE_DESC, FINISHED_ON_DESC]) {
  	lists {
  	  name
  	  # status
      entries {
        media {
          title {
            romaji
          }
          # meanScore
          # siteUrl
          format
          relations
        }
        # status
        score (format: POINT_100)
        # progress
        # priority
        # startedAt {
        #   year
        #   month
        #   day
        # }
        # completedAt {
        #   year
        #   month
        #   day
        # }
        # private
      }
  	}
  }
}

# query {
#   User (name: "robert054321") {
#     statistics {
#       # anime {
#       #   # staff {
#       #   #   staff {
#       #   #     name {
#       #   #       first
#       #   #       middle
#       #   #       last
#       #   #       full
#       #   #       native
#       #   #       userPreferred
#       #   #     }
#       #   #   }
#       #   #   minutesWatched
#       #   # }
#       #   voiceActors {
#       #     voiceActor {
#       #       name {
#       #         full
#       #         native
#       #       }
#       #     }
#       #     minutesWatched
#       #     mediaIds
#       #     meanScore
#       #     characterIds
#       #   }
#       # }
#       manga {
#         staff {
#           staff {
#             name {
#               full
#               native
#             }
#           }
#           chaptersRead
#           meanScore
#           mediaIds
#         }
#         voiceActors {
#           voiceActor {
#             name {
#               full
#               native
#             }
#           }
#           minutesWatched
#           mediaIds
#           characterIds
#         }
#       }
#     }
#   }
# }
