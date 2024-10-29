# mutation($mediaId:Int,$status:MediaListStatus){
#     SaveMediaListEntry(mediaId:$mediaId,status:$status,score:$score){
#         status
#         idea
#         score
#     }
# }
#
mutation($mediaId:Int,$progress:Int){
    SaveMediaListEntry(mediaId:$mediaId,progress:$progress){
        progress
        # status
    }
}

# mutation($mediaId:Int,$progressVolumes:Int,$status:MediaListStatus){
#     SaveMediaListEntry(mediaId:$mediaId,progressVolumes:$progressVolumes,status:$status){
#         progressVolumes
#         status
#     }
# }

# mutation($listEntryId:Int){
#     DeleteMediaListEntry(id:$listEntryId){
#         deleted
#     }
# }

# mutation($listEntryIds:[Int],$status:MediaListStatus){
#     UpdateMediaListEntries(ids:$listEntryIds,status:$status){
#         status
#     }
# }
#
# mutation($mediaId:Int,$notes:String){
#     SaveMediaListEntry(mediaId:$mediaId,notes:$notes){
#         notes
#     }
# }

# mutation($mediaId:Int,$tagId:Int,$vote:Int){
#     SaveMediaTagVote(mediaId:$mediaId,tagId:$tagId,vote:$vote) {
#         mediaId
#         tagId
#         vote
#     }
# }
