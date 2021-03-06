#!/usr/bin/env python


import random
import json
from collections import defaultdict
from twisted.web import server, resource
from twisted.internet import reactor

VERSION = 0.1

#TODO: unlink
#TODO: create game interface
#TODO: limit links per turn (3 + 3*cores)

class Player:
    def __init__(self, name, beginnode):
        self.name = name
        self.beginnode = beginnode
        self.time = 0
        self.wins = False
        self.lost = False

    def __hash__(self):
        return hash(self.name)

    def tick(self):
        self.time += 1

    def dict(self):
        return {
            'name': self.name,
            'beginx': self.beginnode.x,
            'beginy': self.beginnode.y,
            'time': self.time,
            'wins': self.wins,
            'lost': self.lost
        }


class NodeType:
    def __init__(self, id, label, description, resistance, consumption, vision, buildduration, resistancemodifier=1, hidden=False):
        self.id = id
        self.label = label
        self.description = description
        self.resistance = resistance
        self.consumption = consumption #power consumption
        self.vision = vision
        self.buildduration = buildduration #in turns
        self.resistancemodifier = resistancemodifier

    def dict(self):
        return {
            'id': self.id,
            'label': self.label,
            'description': self.description,
            'resistance': self.resistance,
            'consumption': self.consumption,
            'vision': self.vision,
            'buildduration': self.buildduration,
            'resistancemodifier': self.resistancemodifier,
        }

class Event:
    def __init__(self, id, label, priority):
        self.id = id
        self.label = label
        self.priority = priority

    def dict(self):
        return {
                'id': self.name,
                'label': self.label,
                'priority': self.priority
        }


class NonNeighbourLink(Exception):
    pass

class NotEnoughPower(Exception):
    pass

class CommunicationError(Exception):
    pass

class VersionError(Exception):
    pass

class Waiting(Exception):
    pass

class GameOver(Exception):
    pass


nodetypes = {
    'unspecialised':  NodeType('unspecialised',"Unspecialised node","A regular unspecialised node", 1, 10, 1,1,1),
    'shield':  NodeType('shield',"Shielded node","Shielded nodes are hardened nodes and are more resistant to enemy takeover", 5, 50, 1, 2, 1),
    'sabotage':  NodeType('sabotage',"Sabotage node","Sabotage nodes halve the resistance of incoming enemy nodes and have fairly high resistance themselves. Good for instant counterattacks.", 4, 200, 1, 3, 0.5),
    'attack':  NodeType('attack',"Attack node","Attack nodes halve the resistance of enemy nodes you link to, and have moderate resistance themselves.", 3, 150, 1, 2, 0.5),
    'corruption':  NodeType('corruption',"Corruption node","Corruption nodes irreversibly poison their own subgrid when assimilated by the enemy, making the spot cost power instead of yield power and making it very undesireable to own", 0, 200, 1, 3,1 ),
    'destructor':  NodeType('destructor',"Destruction node","Destroys any specialisation on neighbouring enemy nodes when an attempt to assimilate it is made", 2, 200, 1, 3,1 ),
    'sensor':  NodeType('sensor',"Sensor node","Sensor nodes provide an enhanced field of vision", 2, 100, 3, 2, 1 ),
    'core':  NodeType('core',"Core node","Core nodes enable you to regulate your network's power flow. Without a core node, the whole network falls apart. They are veritable but power-hungry fortresses of resistance and they double the resistance of linked neighbouring nodes", 20, 1000, 1, 10, 2),
    'collaborator':  NodeType('collaborator',"Collaborator node","Feeds power to other players, outgoing connections from the collaborator are never assimilations but give power away and thus allow the formation of alliances and conspiracies", 1, 200, 1, 1, 1 ),
}

events = {
    'lostnode': Event('lostnode', "Node was lost due to insufficient power!",2),
    'lostcloak': Event('lostcloak', "Node lost its cloak due to insufficient power!",3),
    'lostspec': Event('lostspec', "Node lost its specialisation due to insufficient power!",4),
    'lostassimilated': Event('lostassimilated', "Node was taken over by the enemy!",1),
    'assimilatesuccess': Event('assimilatesuccess', "Node succesfully assimilated!",5),
    'powerincrease': Event('powerincrease', "Node received more energy",7),
    'powerdecrease': Event('powerdecrease', "Node now has less energy",6),
    'corruption': Event('corruption', "Corruption took place! The subgrid got poisoned!",1),
    'destruction': Event('destruction', "Your specialisation was destroyed!",1),
}

#whether a node will specialise or not is dependent on its power, if it specialises, it does so according to thes probabilities:
seed_defaultspecprobs = {
    (0.8, nodetypes['shield']),
    (0.1, nodetypes['sabotage']),
    (0.05, nodetypes['destructor']),
    (0.04, nodetypes['corruption']),
}
seed_defaulthideprob = 0.02
seed_defaulthideprob_spec = 0.25
seed_defaulthighpowerprob = 0.02
seed_defaultnonodeprob = 0.16
seed_defaultbeginpower = 2000
seed_defaultnullcores = 1

class Game:
    def __init__(self, name, width, height, seed_beginpower= seed_defaultbeginpower, seed_nonodeprob=seed_defaultnonodeprob, seed_specprobs=seed_defaultspecprobs, seed_hideprob=seed_defaulthideprob, seed_hideprob_spec = seed_defaulthideprob_spec, seed_highpowerprob = seed_defaulthighpowerprob):
        self.name = name
        self.width = width
        self.height = height
        self.players = []
        self.nodes =  defaultdict(dict) # x => y => Node
        self.time = 0
        self.createnodes(seed_nonodeprob, seed_specprobs, seed_highpowerprob, seed_hideprob, seed_hideprob_spec)

        #self.changednodes = set() #will hold all changed nodes after a tick, needed to update clients
        self.visiblenodes = defaultdict(set) #will hold all visible nodes for each player

    def dict(self):
        return {
                'name': self.name,
                'players': [ p.dict() for p in self.players ],
                'width': self.width,
                'height': self.height,
                'time': self.time,
                'version': self.version
        }

    def __iter__(self):
        for d in self.nodes.values():
            for node in d.values():
                yield node

    def makebeginnode(self, seed_beginpower):
        valid = False
        while not valid:
            node = random.choice(iter(self))
            if node.type == 'unspecialised':
                neighbours = list(node.neighbours())
                if len(neighbours) >= 6:
                    node.type = nodetypes['core']
                    node.power = seed_beginpower
                    valid = True


    def addplayer(self, name):
        beginnode = self.makebeginnode(seed_defaultbeginpower)
        player = Player(name, beginnode)
        self.players.append(player)
        beginnode.owner = player


    def createnodes(self, seed_nonodeprob, seed_specprobs, seed_highpowerprob, seed_hideprob, seed_hideprob_spec, seed_nullcores = seed_defaultnullcores, seed_beginpower = seed_defaultbeginpower):
        for x in range(1,self.width+1):
            for y in range(1,self.height+1):
                if random.random() <= seed_nonodeprob:
                    continue

                power = random.expovariate(1)*10 #exponential distribution
                if random.random() <= seed_highpowerprob: #chance for a extra high power node
                    power = power * power #square


                hidden = (random.random() < seed_hideprob)

                type = nodetypes['unspecialised']
                hidden = False
                if power > 0:
                    specprob = 1/power
                    if random.random() <= specprob:
                        hidden = (random.random() < seed_hideprob_spec)
                        r = random.random()
                        summed = 0
                        for prob, t in seed_specprobs:
                            if r <= summed + t:
                                type = t
                                break
                            summed += t


                self.nodes[x][y] = Node(self, x, y, type, None, power, 0, hidden)

        if seed_nullcores > 0:
            for i in range(0, seed_nullcores+1):
                node = self.beginnode(seed_beginpower)

    def waiting(self):
        for player in self.players:
            if player.time == self.game.time:
                yield player


    def tick(self):
        #one time tick (turn), will be call by post() when last player completes his/her turn
        self.visiblenodes = defaultdict(set)
        self.cores = defaultdict(int)
        for node in self:
            node.tick()
            if node.owner:
                self.visiblenodes[node.owner] |= node.visiblenodes()
            if node.type == nodetypes['core']:
                self.cores[node.owner] += 1

        if len(self.cores) == 1:
            winner = self.cores.keys()[0]
            winner.wins = True
            raise GameOver(winner.name + " wins!")

    def getplayer(self, **kwargs):
        player = None
        if 'player' in kwargs:
            for p in self.players:
                if p.name == kwargs['player']:
                    player = p
        if not player:
            raise CommunicationError("No valid player specified")

        if player.time > self.game.time:
            raise Waiting(",".join(self.waiting))


    def post(self, **kwargs):

        if not 'version' in kwargs:
            raise CommunicationError("No version specified")
        if kwargs.version != VERSION:
            raise VersionError("Client and server versions do not match")


        player = self.getplayer(**kwargs) #may raise Waiting exception
        if player.lost:
            raise GameOver("You lost :'(")

        if not 'command' in kwargs:
            raise CommunicationError("No command specified")



        command = kwargs['command']


        if 'x' in kwargs and 'y' in kwargs:
            try:
                x = int(kwargs['x'])
                y = int(kwargs['y'])
            except:
                raise CommunicationError("Invalid (x,y), not numeric")
            if x in self.nodes and y in self.nodes[x]:
                sourcenode = self.nodes[x][y]
            else:
                raise CommunicationError("Invalid (x,y), no node there")
            if sourcenode.owner != player:
                raise CommunicationError("Sourcenode not owned by player!")
        else:
            sourcenode = None

        if command == 'done':
            player.tick()
            alldone = True
            for p in self.players:
                if p < player.time:
                    alldone = False
            if alldone:
                self.game.tick()
        elif command == 'link':
            if sourcenode is None:
                raise CommunicationError("No sourcenode specified, required for " +command)
            try:
                x = int(kwargs['targetx'])
                y = int(kwargs['targety'])
            except:
                raise CommunicationError("Invalid arguments for " + command )
            if x in self.nodes and y in self.nodes[x]:
                targetnode = self.nodes[x][y]
                sourcenode.link(targetnode)
            else:
                raise CommunicationError("Target node does not exist!")
        elif command == 'spec':
            if sourcenode is None:
                raise CommunicationError("No sourcenode specified, required for " +command)
            try:
                newtype = kwargs['type']
                assert newtype in nodetypes
            except:
                raise CommunicationError("Invalid arguments for " + command + ", expected type")
            sourcenode.specialise(nodetypes[newtype])



    def get(self, **kwargs):
        if 'init' in kwargs and kwargs['init'] == 1:
            #get general status to initialise a client (regardless of player)
            d = {'game': self.dict(), 'nodetypes': self.nodetypes(), 'events': self.events()}
        else:
            player = self.getplayer(**kwargs) #may raise Waiting exception

            #get the state of the game
            if player.lost or player.wins:
                #If you win or lose you get to see all nodes
                d = {'players': [ p.dict() for p in self.players], 'nodes':  [ n.dict() for n in self ]}
            else:
                d = {'players': [ p.dict() for p in self.players], 'nodes':  [ n.dict() for n in self.visiblenodes ]}
        return json.dumps(d)

class Link:
    def __init__(self, source, target, power):
        self.source = source
        self.target = target
        self.power = power

    def __eq__(self, other):
        return (self.source == other.source and self.target == other.target and self.power == other.power)

    def dict(self):
        return {
                'sourcex': self.source.x,
                'sourcey': self.source.y,
                'targetx': self.target.x,
                'targety': self.target.y,
                'power': self.power,
        }


class Node:
    def __init__(self, game, x, y, type, owner, power, buildtime, hidden=False):
        self.game = game
        self.x = x
        self.y = y
        self.type = type
        self.power = power #subgrid power
        self.outlinks = []
        self.inlinks = []
        self.owner = owner
        self.buildtime = buildtime #from what time on is this node built? (may be in future, node will then be in a reconfigure mode and acts as a normal node until done)
        self.hidden = hidden
        self.lastevent = None

    def link(self, targetnode, power):
        if targetnode.x == self.x and targetnode.y == self.y:
            raise NonNeighbourLink()
        if abs(targetnode.x - self.x) > 1 or abs(targetnode.y - self.y) > 1:
            raise NonNeighbourLink()

        for link in self.outlinks:
            if link.target == targetnode: #update existing link
                link.power += power
                link.target.setevent(events['powerincrease'])
                return True


        for i, link in enumerate(self.inlinks):
            if link.source == targetnode and link.source.owner == self.owner: #conflicting reverse link
                if power < link.power:
                     link.power -= power
                     return True
                else:
                    power -= link.power
                    #deletion
                    link.source.inlinks.remove(link)
                    del self.inlinks[i]
                    return True

        link = Link(self, targetnode, power )
        self.outlinks.append(link)
        self.targetnode.inlinks.append(link)

    def hide(self):
        if self.energy - self.type.consumption <= 0:
            raise NotEnoughPower()
        else:
            self.hidden = True


    def energy(self):
        if self.hidden:
            energy = self.power - (self.type.consumption * 2)
        else:
            energy = self.power - self.type.consumption
        for link in self.outlinks:
            if link.owner == self.owner or self.type == nodetypes['collaborator']:
                energy = energy - self.link.power
        for link in self.inlinks:
            if link.owner == self.owner or self.type == nodetypes['collaborator']:
                energy = energy + self.link.power
        return energy

    def strength(self):
        if self.specialising():
            return self.energy()

        if self.specialising():
            resistance = 1
        else:
            resistance = self.resistance
        #check for sabotaging neighbours
        for link in self.outlinks:
            if link.target.type == nodetypes['sabotage'] and link.target.owner != self.owner and not link.target.specialising():
                resistance = resistance * link.target.resistancemodifier
        #check for neighbouring enemy attack nodes (or friendly core nodes)
        for link in self.inlinks:
            if (link.source.type == nodetypes['attack'] and link.source.owner != self.owner and not link.source.specialising()) or (link.source.type == nodetypes['core'] and link.target.owner == self.owner and not link.source.specialising()):
                resistance = resistance * link.target.resistancemodifier

        return resistance * self.energy()

    def specialise(self, type):
        #check whether enough energy
        if self.energy + self.type.consumption - type.consumption <= 0:
            raise NotEnoughPower()

        self.type = type
        self.buildtime = self.gametime + self.type.buildduration

    def specialising(self):
        #is the node currently specialising into something else?
        return self.buildtime > self.game.time


    def onassimilation(self, attacker):
        self.setevent(events["assimilatesuccess"])
        if self.type == nodetypes['corruption']:
            if self.power > 0: #can't reverse corruptions
                self.power = -1 * self.power
                self.tick() #no extra tick, node may be lost again
                self.setevent(events["corruption"])
        elif self.type == 'destructor':
            for link in self.inlinks:
                if link.owner == attacker:
                    if link.source.type != nodetypes['unspecialised']:
                        link.source.type = nodetypes['unspecialised']
        elif self.type == 'core':
            self.type = nodetypes['unspecialised']
            #does the player have a core left?
            defeat = True
            for node in self:
                if node.type == 'core' and node.owner == self.owner:
                    defeat = False
                    break
            if defeat:
                self.owner.lost = True
                #disown all the player's nodes, specs remain however!
                for node in self:
                    if node.owner == self.owner:
                        node.owner = None



        self.type = nodetypes['unspecialised']
        self.hidden = False


    def tick(self):
        if self.type is None:
            return False

        #Check ownership

        #is an enemy attack in progress? If multiple attackers, the strongest wins
        attackpower = defaultdict(int)
        for link in self.inlinks:
            if link.owner != self.owner and link.source.type != nodetypes['collaborator']:
                attackpower[link.source] += link.power
        for attacker, attack in sorted(attackpower.items(), key= lambda x: x * -1):
            if attack > self.strength():
                self.onassimilation(attacker)
                self.owner = attacker
                self.game.changednodes.add(self)
                break

        #does the node receive enough pwoer to sustain itself?
        while self.energy() <= 0 and self.owner != None:
            #No!
            if self.hidden:
                #drop cloak, unhide
                self.hidden = False
                self.setevent(events["lostcloak"])
            elif self.type != nodetypes['unspecialised']:
                #drop specialisation
                self.type = nodetypes['unspecialised']
                self.setevent(events["lostspec"])
            else:
                #drop ownership
                self.owner = None
                #delete links
                self.setevent(events["lostnode"])
            self.game.changednodes.add(self)

        return True


    def setevent(self, event):
        if self.lastevent is None or event.priority > self.lastevent.priority:
            self.lastevent = event


    def neighbours(self, depth = 1):
        for x in range(min(1,self.x - depth), min(self.x + depth + 1,self.game.width) ):
            for y in range(min(1,self.y - depth), min(self.y + depth + 1,self.game.height) ):
                if x != self.x and y != self.y:
                    if y in self.game.nodes[x]:
                        yield self.game.nodes[x][y]

    def visiblenodes(self):
        if self.specialising():
            return set([n for n in self.neighbours(1) if n.owner != self.owner])
        else:
            return set([n for n in self.neighbours(self.vision) if n.owner != self.owner])

    def dict(self):
        #dictionary representation for clients (serialisable to json)
        return {
                'x': self.x,
                'y': self.y,
                'type': self.type.id,
                'power': self.power,
                'energy': self.energy(),
                'strength': self.strength(),
                'owner': self.owner.name,
                'buildtime': self.buildtime,
                'hidden': self.hidden,
                'outlinks': [ link.dict() for link in self.outlinks ],
                'inlinks': [ link.dict() for link in self.inlinks ],
                'lastevent': self.lastevent.label if self.lastevent else "",
                'lasteventpriority': self.lastevent.priority if self.lastevent else 100,
        }



class GameResource(resource.Resource):
    def __init__(self, game):
        self.game = game

    def render_GET(self, request):
        try:
            request.setHeader('Content-Type', "application/json")
            return self.game.get(**request.args)
        except CommunicationError as e:
            request.setResponseCode(403)
            return str(e)
        except Waiting as e:
            request.setHeader('Content-Type', "application/json")
            return "{ 'error': 'waiting', 'errormsg': 'Waiting for other players to complete their turn' }"

    def render_POST(self, request):
        try:
            request.setHeader('Content-Type', "application/json")
            return self.game.post(**request.args)
        except CommunicationError as e:
            request.setResponseCode(403)
            return str(e)
        except Waiting as e:
            request.setHeader('Content-Type', "application/json")
            return "{ 'error': 'waiting',  'errormsg': \"" +  str(e) + "\" }"
        except NotEnoughPower as e:
            request.setHeader('Content-Type', "application/json")
            return "{ 'error': 'notenoughpower', 'errormsg': \"" +  str(e) + "\" }"
        except GameOver as e:
            request.setHeader('Content-Type', "application/json")
            return "{ 'gameover': 1 }"


class IndexResource(resource.Resource):
    def __init__(self, games):
        self.games = games

    def getChild(self, game, request):
        if game in self.games:
            return GameResource(self.games[game])
        else:
            request.setResponseCode(404)
            return "Game not found"

class BattleNodeServer:
    def __init__(self, port):
        assert isinstance(port, int)
        self.games = {}
        reactor.listenTCP(port, server.Site(IndexResource(self.games)))
        reactor.run()


def main():
    BattleNodeServer(7455)

if __name__ == '__main__':
    main()
