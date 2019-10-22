import os.path
import re
import time
import datetime
import socket
from collections import namedtuple
import subprocess
from contextlib import contextmanager

try:
    from ecl.summary import EclSum
except ImportError:
    from ert.ecl import EclSum

from .ecl_config import EclConfig


EclipseResult = namedtuple("EclipseResult" , "errors bugs")
body_sub_pattern = "(\s^\s@.+$)*"
date_sub_pattern = "\s+AT TIME\s+(?P<Days>\d+\.\d+)\s+DAYS\s+\((?P<Date>(.+)):\s*$"
error_pattern    = "^\s@--  ERROR%s$%s"   % (date_sub_pattern, body_sub_pattern)

def make_LSB_MCPU_machine_list( LSB_MCPU_HOSTS ):
    host_numcpu_list = LSB_MCPU_HOSTS.split()
    host_list = []
    for index in range(len(host_numcpu_list) / 2):
        machine = host_numcpu_list[ 2*index ]
        host_numcpu = int(host_numcpu_list[ 2*index  + 1 ])
        for icpu in range(host_numcpu):
            host_list.append( machine )
    return host_list



def make_LSB_machine_list( LSB_HOSTS ):
    return LSB_HOSTS.split()


@contextmanager
def pushd(run_path):
    starting_directory = os.getcwd()
    os.chdir(run_path)
    yield
    os.chdir(starting_directory)


class EclRun(object):
    """Wrapper class to run Eclipse simulations.

    The EclRun class is a small wrapper class which is used to run Eclipse
    simulations. It will load a configuration, i.e. where the binary is
    installed and so on, from an instance of the EclConfig class.

    The main method is the runEclipse() method which will:

      1. Set up redirection of the stdxxx file descriptors.
      2. Set the necessary environment variables.
      3. [MPI]: Create machine_file listing the nodes which should be used.
      4. fork+exec to actually run the Eclipse binary.
      5. Parse the output .PRT / .ECLEND file to check for errors.

    If the simulation fails the runEclipse() method will raise an exception.

    The class is called EclRun, and the main focus has been on running Eclipse
    simulations, but it should also handle "eclipse-like" simulators, e.g. the
    simulator OPM/flow.

    To actually create an executable script based on this class could in it's
    simplest form be:

       #!/usr/bin/env python
       import sys
       from res.fm.ecl import EclRun

       run = EclRun()
       run.runEclipse( )


    """

    def __init__(self , ecl_case, sim, num_cpu = 1, check_status = True):
        self.sim = sim
        self.check_status = check_status
        self.num_cpu = int(num_cpu)
        if self.num_cpu > 1:
            if self.sim.mpirun is None:
                raise Exception("Internal inconsistency - asked for:{} cpus with a not MPI enabled simulator".format(num_cpu))


        # Dechipher the ecl_case argument.
        input_arg = ecl_case
        (base , ext) = os.path.splitext( input_arg )
        if ext and ext in [".data", ".DATA"]:
            data_file = input_arg
        else:
            if input_arg.islower():
                data_file = input_arg + ".data"
            else:
                data_file = input_arg + ".DATA"


        if not os.path.isfile( data_file ):
            raise IOError("No such file: %s" % data_file )
        else:
            (self.run_path , self.data_file)  = os.path.split( data_file )
            (self.base_name , ext ) = os.path.splitext( self.data_file )

            if self.run_path is None:
                self.run_path = os.getcwd()
            else:
                self.run_path = os.path.abspath( self.run_path )



    def runPath(self):
        return self.run_path


    def baseName(self):
        return self.base_name


    def numCpu(self):
        return self.num_cpu



    def initEnv(self):
        for var,value in self.sim.env.items():
            os.environ[var] = value



    def initMPI(self):

        # If the environment variable LSB_MCPU_HOSTS is set we assume the job is
        # running on LSF - otherwise we assume it is running on the current host.
        #
        # If the LSB_MCPU_HOSTS variable is indeed set it will be a string like this:
        #
        #       host1 num_cpu1 host2 num_cpu2 ...
        #
        # i.e. an alternating list of hostname & number of
        # cpu. Alternatively/in addition the environment variable
        # LSB_HOSTS can be used. This variable is simply:
        #
        #       host1  host1  host2  host3



        LSB_MCPU_HOSTS = os.getenv("LSB_MCPU_HOSTS")
        LSB_HOSTS = os.getenv("LSB_HOSTS")

        if LSB_MCPU_HOSTS or LSB_HOSTS:
            LSB_MCPU_machine_list = make_LSB_MCPU_machine_list( LSB_MCPU_HOSTS )
            LSB_machine_list = make_LSB_machine_list( LSB_HOSTS )

            if len(LSB_MCPU_machine_list) == self.num_cpu:
                machine_list = LSB_MCPU_machine_list
            elif len(LSB_machine_list) == self.num_cpu:
                machine_list = LSB_machine_list
            else:
                raise Exception("LSF / MPI problems. Asked for:%s cpu. LSB_MCPU_HOSTS: \"%s\"  LSB_HOSTS: \"%s\"" % (self.num_cpu , LSB_MCPU_HOSTS , LSB_HOSTS))
        else:
            localhost = socket.gethostname()
            machine_list = [ localhost ] * self.num_cpu


        self.machine_file = "%s.mpi" % self.base_name
        with open( self.machine_file , "w") as fileH:
            for host in machine_list:
                fileH.write("%s\n" % host)


    def execSerialEclipse(self):
        process = subprocess.Popen(
            [
                self.sim.executable,
                self.base_name
            ],
            env=self.sim.env
        )
        process.communicate()
        return process.returncode


    def execParallellEclipse(self):
        self.initMPI( )
        process = subprocess.Popen(
            [
                self.sim.mpirun,
                "-machinefile",
                self.machine_file,
                "-np",
                "%s" % self.num_cpu,
                self.sim.executable,
                self.base_name
            ],
            env=self.sim.env
        )
        process.communicate()
        return process.returncode


    def execEclipse(self):
        with pushd(self.run_path):

            if not os.path.exists( self.data_file ):
                raise IOError("Can not find data_file:%s" % self.data_file )

            if not os.access( self.data_file , os.R_OK ):
                raise OSError("Can not read data file:%s" % self.data_file )

            if self.num_cpu == 1:
                return self.execSerialEclipse()
            else:
                return self.execParallellEclipse()



    def runEclipse(self):
        return_code = self.execEclipse( )

        OK_file = os.path.join(self.run_path , "%s.OK" % self.base_name)
        if not self.check_status:
            with open(OK_file, "w") as f:
                f.write("ECLIPSE simulation complete - NOT checked for errors.")
        else:
            if return_code != 0:
                raise Exception("The eclipse executable:%s exited with error status: %d" % (self.sim.executable, return_code))

            self.assertECLEND( )
            if self.num_cpu > 1:
                self.summary_block( )

            with open(OK_file, "w") as f:
                f.write("ECLIPSE simulation OK")


    def summary_block(self):
        case = os.path.join(self.run_path, self.base_name)
        start_time = datetime.datetime.now( )
        prev_len = 0
        while True:
            dt = datetime.datetime.now() - start_time
            if dt.total_seconds( ) > 15:
                # We have not got a stable summary file after 15 seconds of waiting,
                # this eitther implies that something is completely broken or this is
                # a NOSIM simulation. Due the possibility of NOSIM solution we just return
                # here without signalling an error.
                return None

            time.sleep(1)

            try:
                ecl_sum = EclSum(case)
            except:
                continue

            this_len = len(ecl_sum)
            if prev_len == 0:
                prev_len = this_len
                continue

            if prev_len == this_len:
                break

        return ecl_sum


    def assertECLEND(self):
        result = self.readECLEND( )
        if result.errors > 0:
            error_list = self.parseErrors( )
            sep = "\n\n...\n\n"
            error_msg = sep.join( error_list )
            raise Exception("Eclipse simulation failed with:%d errors:\n\n%s" % (result.errors , error_msg))

        if result.bugs > 0:
            raise Exception("Eclipse simulation failed with:%d bugs" % result.bugs )



    def readECLEND(self):
        error_regexp = re.compile("^\s*Errors\s+(\d+)\s*$")
        bug_regexp = re.compile("^\s*Bugs\s+(\d+)\s*$")

        report_file = os.path.join( self.run_path , "{}.ECLEND".format(self.base_name))
        if not os.path.isfile(report_file):
            report_file = os.path.join( self.run_path, "{}.PRT".format(self.base_name))

        with open(report_file , "r") as fileH:
            for line in fileH.readlines():
                error_match = re.match(error_regexp , line)
                if error_match:
                    errors = int( error_match.group(1) )

                bug_match = re.match(bug_regexp , line)
                if bug_match:
                    bugs = int( bug_match.group(1) )

        return EclipseResult( errors = errors , bugs = bugs )


    def parseErrors(self):
        prt_file = os.path.join( self.runPath() , "%s.PRT" % self.baseName())
        error_list = []
        error_regexp = re.compile(error_pattern, re.MULTILINE)
        with open(prt_file) as f:
            content = f.read()

        offset = 0
        while True:
            match = error_regexp.search( content[offset:] )
            if match:
                error_list.append( content[ offset + match.start( ) : offset + match.end() ] )
                offset += match.end( )
            else:
                break

        return error_list


    @classmethod
    def checkCase(cls , refcase , simcase):
        ref = EclSum( refcase )
        sim = EclSum( simcase )

        if sim.getEndTime( ) >= ref.getEndTime():
            with open("CHECK_ECLIPSE_RUN.OK","w") as f:
                f.write("OK - the simulation %s was >= %s" % (simcase , refcase))

            return True
        else:
            msg = """
CHECK_ECLIPSE_RUN: Failed
Refcase    %s : %s
Simulation %s : %s
""" % ( refcase , ref.getEndTime() , simcase , sim.getEndTime())
            raise ValueError( msg )
