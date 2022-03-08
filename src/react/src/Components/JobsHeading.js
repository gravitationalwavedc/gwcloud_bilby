import React from 'react';
import { Button } from 'react-bootstrap';
import { HiOutlinePlus } from 'react-icons/hi';
import Link from 'found/Link';

const JobsHeading = ({ match, router }) => 
    <h1 className="pt-5 mb-4">
        Public Jobs
        <span className="float-right">
            <Link 
                as={Button}
                variant="outline-primary"
                to='/bilby/job-list/' 
                exact 
                match={match} 
                router={router} 
                className="mr-1">
                                    Switch to my jobs
            </Link>
            <Link as={Button} to='/bilby/job-form/' exact match={match} router={router}>
                <HiOutlinePlus size={18} className="mb-1 mr-1"/>
                                Start a new job 
            </Link>
        </span>
    </h1>;

export default JobsHeading;
