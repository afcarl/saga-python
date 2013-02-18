#!/usr/bin/env python
# encoding: utf-8

""" PBS job adaptor implementation
"""

__author__    = "Ole Weidner"
__copyright__ = "Copyright 2013, The SAGA Project"
__license__   = "MIT"

import saga.utils.which
import saga.utils.pty_shell

import saga.adaptors.cpi.base
import saga.adaptors.cpi.job

from saga.job.constants import *

import re
import time
from copy import deepcopy

SYNC_CALL = saga.adaptors.cpi.decorators.SYNC_CALL
ASYNC_CALL = saga.adaptors.cpi.decorators.ASYNC_CALL


# --------------------------------------------------------------------
#
def log_error_and_raise(message, exception, logger):
    logger.error(message)
    raise exception(message)


# --------------------------------------------------------------------
#
def _pbs_to_saga_jobstate(pbsjs):
    """ translates a pbs one-letter state to saga
    """
    if pbsjs == 'C':
        return saga.job.DONE
    elif pbsjs == 'E':
        return saga.job.RUNNING
    elif pbsjs == 'H':
        return saga.job.PENDING
    elif pbsjs == 'Q':
        return saga.job.PENDING
    elif pbsjs == 'R':
        return saga.job.RUNNING
    elif pbsjs == 'T':
        return saga.job.RUNNING
    elif pbsjs == 'W':
        return saga.job.PENDING
    elif pbsjs == 'S':
        return saga.job.PENDING
    elif pbsjs == 'X':
        return saga.job.CANCELED
    else:
        return saga.job.UNKNOWN


# --------------------------------------------------------------------
#
def _pbscript_generator(url, logger, jd, ppn, is_cray=False):
    """ generates a PBS script from a SAGA job description
    """
    pbs_params = str()
    exec_n_args = str()

    if jd.executable is not None:
        exec_n_args += "%s " % (jd.executable)
    if jd.arguments is not None:
        for arg in jd.arguments:
            exec_n_args += "%s " % (arg)

    if jd.name is not None:
        pbs_params += "#PBS -N %s \n" % jd.name

    pbs_params += "#PBS -V     \n"

    if jd.environment is not None:
        variable_list = str()
        for key in jd.environment.keys():
            variable_list += "%s=%s," % (key, jd.environment[key])
        pbs_params += "#PBS -v %s \n" % variable_list

    if jd.working_directory is not None:
        pbs_params += "#PBS -d %s \n" % jd.working_directory
    if jd.output is not None:
        pbs_params += "#PBS -o %s \n" % jd.output
    if jd.error is not None:
        pbs_params += "#PBS -e %s \n" % jd.error
    if jd.wall_time_limit is not None:
        hours = jd.wall_time_limit / 60
        minutes = jd.wall_time_limit % 60
        pbs_params += "#PBS -l walltime=%s:%s:00 \n" \
            % (str(hours), str(minutes))
    if jd.queue is not None:
        pbs_params += "#PBS -q %s \n" % jd.queue
    if jd.project is not None:
        pbs_params += "#PBS -A %s \n" % str(jd.project)
    if jd.job_contact is not None:
        pbs_params += "#PBS -m abe \n"

    # TORQUE on a cray requires different -l size.. arguments than regular
    # HPC clusters:
    if is_cray is True:
        # Special case for TORQUE on Cray XT5s
        logger.info("Using Cray XT specific flags: '-l size=xx'")
        if jd.total_cpu_count is not None:
            pbs_params += "#PBS -l size=%s \n" % jd.total_cpu_count
    else:
        # Default case, i.e, standard HPC cluster (non-Cray XT)
        if jd.total_cpu_count is not None:
            tcc = int(jd.total_cpu_count)
            tbd = float(tcc) / float(ppn)
            if float(tbd) > int(tbd):
                pbs_params += "#PBS -l nodes=%s:ppn=%s \n" \
                    % (str(int(tbd) + 1), ppn)
            else:
                pbs_params += "#PBS -l nodes=%s:ppn=%s \n" \
                    % (str(int(tbd)), ppn)

    pbscript = "\n#!/bin/bash \n%s%s" % (pbs_params, exec_n_args)
    return pbscript


# --------------------------------------------------------------------
# some private defs
#
_PTY_TIMEOUT = 2.0

# --------------------------------------------------------------------
# the adaptor name
#
_ADAPTOR_NAME          = "saga.adaptor.pbsjob"
_ADAPTOR_SCHEMAS       = ["pbs", "pbs+ssh", "pbs+gsissh"]
_ADAPTOR_OPTIONS       = [
    {
    'category':      'saga.adaptor.pbsjob',
    'name':          'foo',
    'type':          bool,
    'default':       False,
    'valid_options': [True, False],
    'documentation': """Create a detailed debug trace on the remote host.
                        Note that the log is *not* removed, and can be large!
                        A log message on INFO level will be issued which
                        provides the location of the log file.""",
    'env_variable':   None
    },
]

# --------------------------------------------------------------------
# the adaptor capabilities & supported attributes
#
_ADAPTOR_CAPABILITIES = {
    "jdes_attributes":   [saga.job.NAME,
                          saga.job.EXECUTABLE,
                          saga.job.ARGUMENTS,
                          saga.job.ENVIRONMENT,
                          saga.job.INPUT,
                          saga.job.OUTPUT,
                          saga.job.ERROR,
                          saga.job.QUEUE,
                          saga.job.PROJECT,
                          saga.job.WALL_TIME_LIMIT,
                          saga.job.WORKING_DIRECTORY,
                          saga.job.TOTAL_CPU_COUNT],
    "job_attributes":    [saga.job.EXIT_CODE,
                          saga.job.EXECUTION_HOSTS,
                          saga.job.CREATED,
                          saga.job.STARTED,
                          saga.job.FINISHED],
    "metrics":           [saga.job.STATE,
                          saga.job.STATE_DETAIL],
    "contexts":          {"ssh":      "SSH public/private keypair",
                          "x509":     "X509 proxy for gsissh",
                          "userpass": "username/password pair for simple ssh"}
}

# --------------------------------------------------------------------
# the adaptor documentation
#
_ADAPTOR_DOC = {
    "name":          _ADAPTOR_NAME,
    "cfg_options":   _ADAPTOR_OPTIONS,
    "capabilities":  _ADAPTOR_CAPABILITIES,
    "description":   """The PBS job adaptor. This adaptor can run jobs on
                        PBS clusters.""",
    "details": """ A more elaborate description....""",
    "schemas": {"pbs":   "use a local PBS installations",
               "pbs+ssh":    "use ssh to conenct to a remote PBS cluster",
               "pbs+gsissh": "use gsissh to connect to a remote PBS cluster"}
}

# --------------------------------------------------------------------
# the adaptor info is used to register the adaptor with SAGA

_ADAPTOR_INFO = {
    "name":    _ADAPTOR_NAME,
    "version": "v0.1",
    "schemas": _ADAPTOR_SCHEMAS,
    "cpis": [
        {
        "type": "saga.job.Service",
        "class": "PBSJobService"
        },
        {
        "type": "saga.job.Job",
        "class": "PBSJob"
        }
    ]
}


###############################################################################
# The adaptor class
class Adaptor (saga.adaptors.cpi.base.AdaptorBase):
    """
    This is the actual adaptor class, which gets loaded by SAGA (i.e. by the
    SAGA engine), and which registers the CPI implementation classes which
    provide the adaptor's functionality.
    """

    # ----------------------------------------------------------------
    #
    def __init__(self):

        saga.adaptors.cpi.base.AdaptorBase.__init__(self,
            _ADAPTOR_INFO, _ADAPTOR_OPTIONS)

        self.id_re = re.compile('^\[(.*)\]-\[(.*?)\]$')
        self.opts = self.get_config()
        self.foo = self.opts['foo'].get_value()

        #self._logger.info('debug trace : %s' % self.debug_trace)

    # ----------------------------------------------------------------
    #
    def sanity_check(self):

        # FIXME: also check for gsissh

        pass

    def parse_id(self, id):
        # split the id '[rm]-[pid]' in its parts, and return them.

        match = self.id_re.match(id)

        if not match or len(match.groups()) != 2:
            raise saga.BadParameter("Cannot parse job id '%s'" % id)

        return (match.group(1), match.group(2))


###############################################################################
#
class PBSJobService (saga.adaptors.cpi.job.Service):
    """ implements saga.adaptors.cpi.job.Service """

    # ----------------------------------------------------------------
    #
    def __init__(self, api, adaptor):

        self._cpi_base = super(PBSJobService, self)
        self._cpi_base.__init__(api, adaptor)

    # ----------------------------------------------------------------
    #
    def __del__(self):

        # FIXME: not sure if we should PURGE here -- that removes states which
        # might not be evaluated, yet.  Should we mark state evaluation
        # separately?
        #   cmd_state () { touch $DIR/purgeable; ... }
        # When should that be done?
        self._logger.error("adaptor dying... %s" % self.njobs)
        self._logger.trace()

        self.finalize(kill_shell=True)

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def init_instance(self, adaptor_state, rm_url, session):
        """ Service instance constructor """

        self.rm      = rm_url
        self.session = session
        self.njobs   = 0
        self.ppn     = 0
        self.is_cray = False

        rm_scheme = rm_url.scheme
        pty_url   = deepcopy(rm_url)

        # we need to extrac the scheme for PTYShell. That's basically the
        # job.Serivce Url withou the pbs+ part. We use the PTYShell to execute
        # pbs commands either locally or via gsissh or ssh.
        if rm_scheme == "pbs":
            pty_url.scheme = "fork"
        elif rm_scheme == "pbs+ssh":
            pty_url.scheme = "ssh"
        elif rm_scheme == "pbs+gsissh":
            pty_url.scheme = "gsissh"

        # these are the commands that we need in order to interact with PBS.
        # the adaptor will try to find them during initialize(self) and bail
        # out in case they are note avaialbe.
        self._commands = {'pbsnodes': None,
                          'qstat':    None,
                          'qsub':     None,
                          'qdel':     None}

        # create a null logger to silence the PTY wrapper!
        import logging

        class NullHandler(logging.Handler):
            def emit(self, record):
                pass
        #nh = NullHandler()
        #null_logger = logging.getLogger("PTYShell").addHandler(nh)

        self.shell = saga.utils.pty_shell.PTYShell(pty_url,
            self.session.contexts)#, null_logger)

        self.shell.set_initialize_hook(self.initialize)
        self.shell.set_finalize_hook(self.finalize)

        self.initialize()

    # ----------------------------------------------------------------
    #
    def initialize(self):
        # check if all required pbs tools are available
        for cmd in self._commands.keys():
            ret, out, _ = self.shell.run_sync("which %s " % cmd)
            if ret != 0:
                message = "Error finding PBS tools: %s" % out
                log_error_and_raise(message, saga.NoSuccess, self._logger)
            else:
                path = out.strip()  # strip removes newline
                if cmd == 'qdel':  # qdel doesn't support --version!
                    self._commands[cmd] = {"path":    path,
                                           "version": "?"}
                else:
                    ret, out, _ = self.shell.run_sync("%s --version" % cmd)
                    if ret != 0:
                        message = "Error finding PBS tools: %s" % out
                        log_error_and_raise(message, saga.NoSuccess,
                            self._logger)
                    else:
                        # version is reported as: "version: x.y.z"
                        version = out.strip().split()[1]

                        # add path and version to the command dictionary
                        self._commands[cmd] = {"path":    path,
                                               "version": version}

        self._logger.info("Found PBS tools: %s" % self._commands)

        # let's try to figure out if we're working on a Cray XT machine.
        # naively, we assume that if we can find the 'aprun' command in the
        # path that we're logged in to a Cray machine.
        ret, out, _ = self.shell.run_sync('which aprun')
        if ret != 0:
            self.is_cray = False
        else:
            self._logger.info("System seems to be a Cray XT class machine.")
            self.is_cray = True

        # see if we can get some information about the cluster, e.g.,
        # different queues, number of processes per node, etc.
        # TODO: this is quite a hack. however, it *seems* to work quite
        #       well in practice.
        ret, out, _ = self.shell.run_sync('%s -a | grep np' % \
            self._commands['pbsnodes']['path'])
        if ret != 0:
            message = "Error running pbsnodes: %s" % out
            log_error_and_raise(message, saga.NoSuccess, self._logger)
        else:
            # this is black magic. we just assume that the highest occurence
            # of a specific np is the number of processors (cores) per compute
            # node. this equals max "PPN" for job scripts
            ppn_list = dict()
            for line in out.split('\n'):
                np = line.split(' = ')
                if len(np) == 2:
                    np = np[1].strip()
                    if np in ppn_list:
                        ppn_list[np] += 1
                    else:
                        ppn_list[np] = 1
            self.ppn = max(ppn_list, key=ppn_list.get)
            self._logger.debug("Found the following 'ppn' configurations: %s. Using %s as default ppn." 
                % (ppn_list, self.ppn))

    # ----------------------------------------------------------------
    #
    def finalize(self, kill_shell=False):
        pass

    # ----------------------------------------------------------------
    #
    def _job_run(self, jd):
        """ runs a job via qsub
        """

        # create a PBS job script from SAGA job description
        script = _pbscript_generator(url=self.rm, logger=self._logger, jd=jd,
            ppn=self.ppn, is_cray=self.is_cray)
        self._logger.debug("Generated PBS script: %s" % script)

        ret, out, _ = self.shell.run_sync("echo '%s' | %s" \
            % (script, self._commands['qsub']['path']))

        if ret != 0:
            # something went wrong
            message = "Error running 'qsub': %s. Script was: %s" \
                % (out, script)
            log_error_and_raise(message, saga.NoSuccess, self._logger)
        else:
            # stdout contains the job id
            job_id = "[%s]-[%s]" % (self.rm, out.strip())
            self._logger.info("Submitted PBS job with id: %s" % job_id)
            self.njobs += 1
            return job_id

    # ----------------------------------------------------------------
    #
    def _job_get_info(self, id):
        """ get job attributes via qstat
        """

        job_state   = None
        exec_hosts  = None
        exit_status = None
        create_time = None
        start_time  = None
        end_time    = None

        rm, pid = self._adaptor.parse_id(id)

        ret, out, _ = self.shell.run_sync("%s -f1 %s | \
            egrep '(job_state)|(exec_host)|(exit_status)|(ctime)|(start_time)|(comp_time)'" \
            % (self._commands['qstat']['path'], pid))

        if ret != 0:
            # something went wrong
            message = "Error retrieving job info via 'qstat': %s" % out
            log_error_and_raise(message, saga.NoSuccess, self._logger)

        # parse the egrep result. this should look something like this:
        #     job_state = C
        #     exec_host = i72/0
        #     exit_status = 0
        results = out.split('\n')
        for result in results:
            if len(result.split('=')) == 2:
                key, val = result.split('=')
                key = key.strip()  # strip() removes whitespaces at the
                val = val.strip()  # beginning and the end of the string

                if key == 'job_state':
                    job_state = _pbs_to_saga_jobstate(val)
                elif key == 'exec_host':
                    exec_hosts = val.split('+')  # format i73/7+i73/6+...
                elif key == 'exit_status':
                    exit_status = val
                elif key == 'ctime':
                    create_time = val
                elif key == 'start_time':
                    start_time = val
                elif key == 'comp_time':
                    end_time = val

        return (job_state, exec_hosts, exit_status,
                create_time, start_time, end_time)

    # ----------------------------------------------------------------
    #
    def _job_get_exit_code(self, id):
        """ get the job's exit code
        """
        # _job_get_info returns (job_state, exec_hosts, exit_status,
        #                        create_time, start_time)
        return self._job_get_info(id)[2]

    # ----------------------------------------------------------------
    #
    def _job_get_execution_hosts(self, id):
        """ get the job's exit code
        """
        # _job_get_info returns (job_state, exec_hosts, exit_status,
        #                        create_time, start_time)
        return self._job_get_info(id)[1]

    # ----------------------------------------------------------------
    #
    def _job_cancel(self, id):
        """ cancel the job via 'qdel'
        """
        rm, pid = self._adaptor.parse_id(id)

        ret, out, _ = self.shell.run_sync("%s %s\n" \
            % (self._commands['qdel']['path'], pid))

        if ret != 0:
            message = "Error canceling job via 'qdel': %s" % out
            log_error_and_raise(message, saga.NoSuccess, self._logger)

    # ----------------------------------------------------------------
    #
    def _job_wait(self, id, timeout):
        """ wait for the job to finish or fail
        """

        time_start = time.time()
        time_now   = time_start
        rm, pid    = self._adaptor.parse_id(id)

        while True:
            state = self._job_get_info(id)[0]
            if state == saga.job.DONE or \
               state == saga.job.FAILED or \
               state == saga.job.CANCELED:
                    return True
            # avoid busy poll
            time.sleep(0.5)

            # check if we hit timeout
            if timeout >= 0:
                time_now = time.time()
                if time_now - time_start > timeout:
                    return False

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def create_job(self, jd):
        """ implements saga.adaptors.cpi.job.Service.get_url()
        """
        # check that only supported attributes are provided
        for attribute in jd.list_attributes():
            if attribute not in _ADAPTOR_CAPABILITIES["jdes_attributes"]:
                message = "'jd.%s' is not supported by this adaptor" \
                    % attribute
                log_error_and_raise(message, saga.BadParameter, self._logger)

        # this dict is passed on to the job adaptor class -- use it to pass any
        # state information you need there.
        adaptor_state = {"job_service":     self,
                         "job_description": jd,
                         "job_schema":      self.rm.schema
                        }

        return saga.job.Job(_adaptor=self._adaptor,
                            _adaptor_state=adaptor_state)

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def get_url(self):
        """ implements saga.adaptors.cpi.job.Service.get_url()
        """
        return self.rm

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def list(self):
        """ implements saga.adaptors.cpi.job.Service.list()
        """
        ids = []

        ret, out, _ = self.shell.run_sync("%s -a -u `whoami` | grep `whoami`"\
            % self._commands['qstat']['path'])
        if ret != 0:
            message = "failed to list jobs via 'qstat': %s" % out
            log_error_and_raise(message, saga.NoSuccess, self._logger)
        else:
            jobid = "[%s]-[%s]" % (self.rm, out.split()[0])
            ids.append(jobid)

        return ids

  # # ----------------------------------------------------------------
  # #
  # @SYNC_CALL
  # def get_job (self, jobid):
  #     """ Implements saga.adaptors.cpi.job.Service.get_url()
  #     """
  #     if jobid not in self._jobs.values ():
  #         msg = "Service instance doesn't know a Job with ID '%s'" % (jobid)
  #         raise saga.BadParameter._log (self._logger, msg)
  #     else:
  #         for (job_obj, job_id) in self._jobs.iteritems ():
  #             if job_id == jobid:
  #                 return job_obj.get_api ()
  #
  #
  # # ----------------------------------------------------------------
  # #
  # def container_run (self, jobs) :
  #     self._logger.debug ("container run: %s"  %  str(jobs))
  #     # TODO: this is not optimized yet
  #     for job in jobs:
  #         job.run ()
  #
  #
  # # ----------------------------------------------------------------
  # #
  # def container_wait (self, jobs, mode, timeout) :
  #     self._logger.debug ("container wait: %s"  %  str(jobs))
  #     # TODO: this is not optimized yet
  #     for job in jobs:
  #         job.wait ()
  #
  #
  # # ----------------------------------------------------------------
  # #
  # def container_cancel (self, jobs) :
  #     self._logger.debug ("container cancel: %s"  %  str(jobs))
  #     raise saga.NoSuccess ("Not Implemented");


###############################################################################
#
class PBSJob (saga.adaptors.cpi.job.Job):
    """ implements saga.adaptors.cpi.job.Job
    """

    def __init__(self, api, adaptor):

        # initialize parent class
        self._cpi_base = super(PBSJob, self)
        self._cpi_base.__init__(api, adaptor)

    @SYNC_CALL
    def init_instance(self, job_info):
        """ implements saga.adaptors.cpi.job.Job.init_instance()
        """
        # init_instance is called for every new saga.job.Job object
        # that is created
        self.jd = job_info["job_description"]
        self.js = job_info["job_service"]

        # initialize job attribute values
        self._id              = None
        self._state           = saga.job.NEW
        self._exit_code       = None
        self._exception       = None
        self._created         = None
        self._started         = None
        self._finished        = None
        self._execution_hosts = None

        return self.get_api()

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def get_state(self):
        """ mplements saga.adaptors.cpi.job.Job.get_state()
        """
        # if the state is DONE, CANCELED or FAILED, it is considered
        # final and we don't need to query the backend again
        if self._state == saga.job.CANCELED or self._state == saga.job.FAILED \
            or self._state == saga.job.DONE:
            return self._state
        else:
            try:
                self._state = self.js._job_get_info(self._id)[0]
                return self._state
            except Exception as e:
                if self._id == None:
                    return self._state
                else:
                    raise e

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def wait(self, timeout):
        """ implements saga.adaptors.cpi.job.Job.wait()
        """
        return self.js._job_wait(self._id, timeout)

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def get_id(self):
        """ implements saga.adaptors.cpi.job.Job.get_id()
        """
        return self._id

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def get_exit_code(self):
        """ implements saga.adaptors.cpi.job.Job.get_exit_code()
        """
        if self._exit_code != None:
            return self._exit_code

        self._exit_code = self.js._job_get_exit_code(self._id)
        return self._exit_code

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def get_created(self):
        """ implements saga.adaptors.cpi.job.Job.get_created()
        """
        if self._created is None:
            # _job_get_info returns (job_state, exec_hosts, exit_status,
            #                        create_time, start_time, end_time)
            self._created = self.js._job_get_info(self._id)[3]
        return self._created

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def get_started(self):
        """ implements saga.adaptors.cpi.job.Job.get_started()
        """
        if self._started is None:
            # _job_get_info returns (job_state, exec_hosts, exit_status,
            #                        create_time, start_time, end_time)
            self._started = self.js._job_get_info(self._id)[4]
        return self._started

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def get_finished(self):
        """ implements saga.adaptors.cpi.job.Job.get_finished()
        """
        if self._finished is None:
            # _job_get_info returns (job_state, exec_hosts, exit_status,
            #                        create_time, start_time, end_time)
            self._finished = self.js._job_get_info(self._id)[5]
        return self._finished

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def get_execution_hosts(self):
        """ implements saga.adaptors.cpi.job.Job.get_execution_hosts()
        """
        if self._execution_hosts != None:
            return self._execution_hosts

        self._execution_hosts = self.js._job_get_execution_hosts(self._id)
        return self._execution_hosts

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def cancel(self, timeout):
        """ implements saga.adaptors.cpi.job.Job.cancel()
        """
        self.js._job_cancel(self._id)
        self._state = saga.job.CANCELED

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def run(self):
        """ implements saga.adaptors.cpi.job.Job.run()
        """
        self._id = self.js._job_run(self.jd)

    # ----------------------------------------------------------------
    #
    @SYNC_CALL
    def re_raise(self):
        # nothing to do here actually, as run () is synchronous...
        return self._exception
