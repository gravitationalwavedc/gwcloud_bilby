import React, { useState, useEffect } from 'react';
import {createPaginationContainer, graphql} from 'react-relay';
import { Card, Container, Col } from 'react-bootstrap';
import JobTable from '../Components/JobTable';
import JobsHeading from '../Components/JobsHeading';
import JobSearchForm from '../Components/JobSearchForm';

const RECORDS_PER_PAGE = 100;

const PublicJobs = ({data, match, router, relay}) => {
    const [search, setSearch] = useState('');
    const [timeRange, setTimeRange] = useState('1d');
    const [order, setOrder] = useState();
    const [direction, setDirection] = useState('descending');

    useEffect(() => handleSearchChange(), [search, timeRange, direction, order]);

    const handleSearchChange = () => {
        const refetchVariables = {
            count: RECORDS_PER_PAGE,
            search: search,
            timeRange: timeRange,
            orderBy: order,
            direction: direction
        };
        relay.refetchConnection(1, null, refetchVariables);
    };

    const loadMore = () => {
        if (relay.hasMore()) {
            relay.loadMore(RECORDS_PER_PAGE);
        }
    };

    return (
        <Container fluid>
            <Col md={{offset: 1, span:10}} className="mb-5">
                <JobsHeading 
                    heading="Public Jobs"
                    link={{text: 'Swith to my jobs', path: '/bilby/job-list/'}}
                    match={match}
                    router={router}/>
                <Card className="gw-form-card">
                    <Card.Body>
                        <JobSearchForm
                            search={search}
                            setSearch={setSearch}
                            timeRange={timeRange}
                            setTimeRange={setTimeRange}
                        />
                        <JobTable
                            data={data.publicBilbyJobs} 
                            setOrder={setOrder} 
                            order={order} 
                            setDirection={setDirection} 
                            direction={direction}
                            match={match}
                            router={router}
                            hasMore={relay.hasMore()}
                            loadMore={loadMore}
                            className="mt-4"
                        />
                    </Card.Body>
                </Card>
            </Col>
        </Container>
    );
};

export default createPaginationContainer(PublicJobs,
    {
        data: graphql`
            fragment PublicJobs_data on Query {
                publicBilbyJobs(
                    first: $count,
                    after: $cursor,
                    search: $search,
                    timeRange: $timeRange
                ) @connection(key: "PublicJobs_publicBilbyJobs") {
                    pageInfo {
                      hasNextPage
                      endCursor
                    }
                    edges {
                        node {
                            id
                            user
                            name
                            description
                            jobStatus {
                              name
                            }
                            labels {
                                name
                            }
                            eventId {
                                triggerId
                                eventId
                                nickname
                            }
                        }
                    }
                }
            }
        `,
    },
    {
        direction: 'forward',
        query: graphql`
            query PublicJobsForwardQuery(
                $count: Int!,
                $cursor: String,
                $search: String,
                $timeRange: String
            ) {
              ...PublicJobs_data
            }
        `,

        getConnectionFromProps(props) {
            return props.data && props.data.publicBilbyJobs;
        },

        getFragmentVariables(previousVariables, totalCount) {
            return {
                ...previousVariables,
                count: totalCount
            };
        },
        getVariables(props, {count, cursor}, {}) {
            return {
                count,
                cursor
            };
        }
    }
);
