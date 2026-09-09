"""Predict immutable frames from public applied-input timestamps only."""
from game_reference import LCD
from movement_reference import Player,step
from movement_frames import image

PERIOD=70224
VISIBLE=65664


def visible_boundary(dot):
    return dot>=LCD and (dot-LCD)%PERIOD<VISIBLE


def predict(frame,events):
    """VBlank n updates the software that supplies source frame n+1."""
    assert type(frame) is int and frame>=1,'PHYSICAL_FRAME_NUMBER'
    assert all(events[n][0]<events[n+1][0] for n in range(len(events)-1)),'PHYSICAL_INPUT_ORDER'
    assert all(type(dot) is int and 0<=mask<=255 and visible_boundary(dot) for dot,mask in events),'PHYSICAL_INPUT_WINDOW'
    player=Player();playing=False;mask=0;index=0
    for number in range(frame):
        boundary=LCD+number*PERIOD+VISIBLE
        while index<len(events) and events[index][0]<boundary:
            mask=events[index][1];index+=1
        if not playing and mask&128:playing=True
        if playing:player=step(player,mask)
    return player,playing


def expected_snapshot(metadata,events,epoch):
    dot=metadata['dot'];frame=(dot-LCD)//PERIOD
    assert metadata['epoch']==epoch and metadata['seq']==frame,'PHYSICAL_SNAPSHOT_IDENTITY'
    assert LCD+frame*PERIOD+143*456<=dot<LCD+frame*PERIOD+144*456,'PHYSICAL_SNAPSHOT_COMPLETION'
    player,playing=predict(frame,events)
    return player,image(player,title=not playing)
