"""Native signatures shared by the refinement freeze and read-only delta audit."""
import json
import audit_routed_board as a

def footprints(board):
    out=a.native_footprints(board)
    for f in board.GetFootprints():
        v=out[a.uid(f)];v.update(fpid=str(f.GetFPID().GetLibNickname())+':'+str(f.GetFPID().GetLibItemName()),attributes=f.GetAttributes(),path=f.GetPath().AsString(),models=[dict(filename=m.m_Filename,offset=[m.m_Offset.x,m.m_Offset.y,m.m_Offset.z],scale=[m.m_Scale.x,m.m_Scale.y,m.m_Scale.z],rotation=[m.m_Rotation.x,m.m_Rotation.y,m.m_Rotation.z]) for m in f.Models()])
        for pad in f.Pads():v['pads'][a.uid(pad)].update(roundRectRatio=pad.GetRoundRectRadiusRatio(),maskMargin=str(pad.GetLocalSolderMaskMargin()))
    return json.loads(json.dumps(out))

def copper(item):
    v=a.copper(item)
    if item.GetClass()=='PCB_VIA':v.update(filled=item.GetPrimaryDrillFilledFlag(),capped=item.GetPrimaryDrillCappedFlag())
    return v
